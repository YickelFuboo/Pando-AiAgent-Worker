import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from app.agents.bus.queues import CHANNEL_OUTBOUND_CALLBACKS,MESSAGE_BUS
from app.agents.bus.types import InboundMessage,OutboundMessage
from app.agents.sessions.manager import SESSION_MANAGER
from app.config.settings import PROJECT_BASE_DIR
from app.logger import setup_logging


CLI_CHANNEL_TYPE="cli"
CLI_CHANNEL_ID="local-cli"
CLI_CONFIG_PATH=Path(PROJECT_BASE_DIR)/"data"/".cli_channel"/"config.json"


class CliChannel:
    def __init__(self)->None:
        self._queue:asyncio.Queue[OutboundMessage]=asyncio.Queue()
        self._bus_task:Optional[asyncio.Task]=None
        self.session_id:Optional[str]=None

    async def startup(self)->None:
        if self._bus_task is None or self._bus_task.done():
            self._bus_task=asyncio.create_task(MESSAGE_BUS.run())
        CHANNEL_OUTBOUND_CALLBACKS[CLI_CHANNEL_TYPE]=self._on_outbound

    async def shutdown(self)->None:
        if self._bus_task and not self._bus_task.done():
            self._bus_task.cancel()
            try:
                await self._bus_task
            except asyncio.CancelledError:
                pass
        self._bus_task=None

    def _on_outbound(self,msg:OutboundMessage)->None:
        if self.session_id and msg.session_id==self.session_id:
            self._queue.put_nowait(msg)

    async def init_session(
        self,
        *,
        user_id:str,
        agent_type:str,
        llm_provider:str,
        llm_model:str,
        product_root:str,
    )->str:
        session_id=await SESSION_MANAGER.create_session(
            user_id=user_id,
            agent_type=agent_type,
            channel_type=CLI_CHANNEL_TYPE,
            llm_provider=llm_provider,
            llm_model=llm_model,
            metadata={"product_root":product_root},
        )
        self.session_id=session_id
        return session_id

    async def ask(
        self,
        *,
        content:str,
        user_id:str,
        agent_type:str,
        llm_provider:str,
        llm_model:str,
        product_root:str,
    )->None:
        if not self.session_id:
            raise ValueError("Session not initialized, please run init first.")
        prompt=(
            f"[项目上下文]\n"
            f"产品根目录: {product_root}\n"
            f"请在该目录下完成需求开发，先分析再执行必要代码改动。\n\n"
            f"[需求描述]\n{content}"
        )
        await MESSAGE_BUS.push_inbound(
            InboundMessage(
                channel_type=CLI_CHANNEL_TYPE,
                channel_id=CLI_CHANNEL_ID,
                user_id=user_id,
                session_id=self.session_id,
                agent_type=agent_type,
                content=prompt,
                llm_provider=llm_provider,
                llm_model=llm_model,
                metadata={"product_root":product_root},
            )
        )
        await self._drain_outputs()

    async def _drain_outputs(self)->None:
        quiet_rounds=0
        while True:
            printed=False
            while True:
                try:
                    outbound=self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                text=(outbound.content or "").strip()
                if text:
                    print(f"\n[Agent]\n{text}\n")
                    printed=True
            if printed:
                quiet_rounds=0
            else:
                quiet_rounds+=1
            if await self._is_session_idle() and quiet_rounds>=3:
                break
            await asyncio.sleep(0.4)

    async def _is_session_idle(self)->bool:
        sid=self.session_id
        if not sid:
            return True
        if sid in MESSAGE_BUS.running_agent_pool:
            return False
        mailbox=MESSAGE_BUS.session_mailboxes.get(sid)
        if mailbox and not mailbox.empty():
            return False
        return self._queue.empty()


def _load_config()->dict:
    if not CLI_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CLI_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(data:dict)->None:
    CLI_CONFIG_PATH.parent.mkdir(parents=True,exist_ok=True)
    CLI_CONFIG_PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")


def _resolve_product_root(input_path:Optional[str],config:dict)->str:
    raw=(input_path or config.get("product_root") or "").strip()
    if not raw:
        raise ValueError("请先通过 --product-root 指定产品根目录，或执行 init 时输入。")
    path=Path(raw).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise ValueError(f"产品根目录不存在: {path}")
    return str(path)


async def _run(args:argparse.Namespace)->None:
    config=_load_config()
    user_id=(args.user_id or config.get("user_id") or "cli-user").strip()
    agent_type=(args.agent_type or config.get("agent_type") or "CodingAgent").strip()
    llm_provider=(args.llm_provider or config.get("llm_provider") or "").strip()
    llm_model=(args.llm_model or config.get("llm_model") or "").strip()
    product_root=_resolve_product_root(args.product_root,config)
    cli=CliChannel()
    await cli.startup()
    try:
        session_id=await cli.init_session(
            user_id=user_id,
            agent_type=agent_type,
            llm_provider=llm_provider,
            llm_model=llm_model,
            product_root=product_root,
        )
        config.update(
            {
                "user_id":user_id,
                "agent_type":agent_type,
                "llm_provider":llm_provider,
                "llm_model":llm_model,
                "product_root":product_root,
                "session_id":session_id,
            }
        )
        _save_config(config)
        print(f"CLI init 完成，session_id: {session_id}")

        if args.command=="init":
            return
        if args.command=="ask":
            requirement=(args.requirement or "").strip()
            if not requirement:
                raise ValueError("ask 模式需要传入 requirement。")
            await cli.ask(
                content=requirement,
                user_id=user_id,
                agent_type=agent_type,
                llm_provider=llm_provider,
                llm_model=llm_model,
                product_root=product_root,
            )
            return
        await _interactive_loop(
            cli=cli,
            user_id=user_id,
            agent_type=agent_type,
            llm_provider=llm_provider,
            llm_model=llm_model,
            product_root=product_root,
        )
    finally:
        await cli.shutdown()


async def _interactive_loop(
    *,
    cli:CliChannel,
    user_id:str,
    agent_type:str,
    llm_provider:str,
    llm_model:str,
    product_root:str,
)->None:
    print("进入命令行模式：输入需求描述直接执行；输入 /init 仅重建会话，/exit 退出。")
    while True:
        content=input("需求> ").strip()
        if not content:
            continue
        if content in {"/exit","exit","quit"}:
            return
        if content=="/init":
            session_id=await cli.init_session(
                user_id=user_id,
                agent_type=agent_type,
                llm_provider=llm_provider,
                llm_model=llm_model,
                product_root=product_root,
            )
            print(f"会话已重建: {session_id}")
            continue
        await cli.ask(
            content=content,
            user_id=user_id,
            agent_type=agent_type,
            llm_provider=llm_provider,
            llm_model=llm_model,
            product_root=product_root,
        )


def build_parser()->argparse.ArgumentParser:
    parser=argparse.ArgumentParser(description="Pando Channel CLI")
    parser.add_argument("--product-root",dest="product_root",default=None,help="产品根目录")
    parser.add_argument("--user-id",dest="user_id",default=None,help="用户ID")
    parser.add_argument("--agent-type",dest="agent_type",default=None,help="Agent类型，默认 CodingAgent")
    parser.add_argument("--llm-provider",dest="llm_provider",default=None,help="模型提供方")
    parser.add_argument("--llm-model",dest="llm_model",default=None,help="模型名称")
    subparsers=parser.add_subparsers(dest="command")
    subparsers.add_parser("init",help="初始化CLI配置与会话")
    ask_parser=subparsers.add_parser("ask",help="输入需求描述并调用Agent")
    ask_parser.add_argument("requirement",type=str,nargs="?",default="",help="需求描述")
    return parser


def main()->None:
    setup_logging()
    parser=build_parser()
    args=parser.parse_args()
    if not args.command:
        args.command="interactive"
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\n已退出。")
    except Exception as e:
        logging.error("CLI 运行失败: %s",e)
        raise


if __name__=="__main__":
    main()
