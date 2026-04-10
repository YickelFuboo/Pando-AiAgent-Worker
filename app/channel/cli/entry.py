import argparse
import asyncio
from pathlib import Path
from typing import Callable, Optional
from rich.console import Console
from rich.panel import Panel
from app.agents.bus.queues import CHANNEL_OUTBOUND_CALLBACKS, MESSAGE_BUS
from app.agents.bus.types import InboundMessage,OutboundMessage
from app.agents.sessions.manager import SESSION_MANAGER
from app.config.settings import PROJECT_BASE_DIR
from app.infrastructure.llms.chat_models.factory import llm_factory


CLI_USER_ID="cli-local-user"
CLI_CHANNEL_TYPE="cli"
CLI_CHANNEL_ID="local-cli"
AGENT_ROOT_PATH=Path(PROJECT_BASE_DIR)/"app"/"agents"/".agent"
AGENT_TYPES_WITHOUT_PROJECT_ROOT={"AiAssistant"}


class CliChannel:
    def __init__(self)->None:
        self._queue:asyncio.Queue[OutboundMessage]=asyncio.Queue()
        self.session_id:Optional[str]=None

    async def startup(self)->None:
        CHANNEL_OUTBOUND_CALLBACKS[CLI_CHANNEL_TYPE]=self._on_outbound

    async def shutdown(self)->None:
        CHANNEL_OUTBOUND_CALLBACKS.pop(CLI_CHANNEL_TYPE,None)

    def _on_outbound(self,msg:OutboundMessage)->None:
        if self.session_id and msg.session_id==self.session_id:
            self._queue.put_nowait(msg)

    async def send(
        self,
        *,
        inbound_msg:InboundMessage,
        on_message:Optional[Callable[[str],None]]=None,
    )->list[str]:
        if not self.session_id or not inbound_msg.session_id:
            raise ValueError("Session not initialized, please run /init.")
        await MESSAGE_BUS.push_inbound(inbound_msg)
        return await self._drain_outputs(on_message=on_message)

    async def _drain_outputs(self,*,on_message:Optional[Callable[[str],None]]=None)->list[str]:
        outputs:list[str]=[]
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
                    outputs.append(text)
                    if on_message:
                        on_message(text)
                    printed=True
            if printed:
                quiet_rounds=0
            else:
                quiet_rounds+=1
            if await self._is_session_idle() and quiet_rounds>=3:
                break
            await asyncio.sleep(0.4)
        return outputs

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


class CliRuntime:
    def __init__(self,args:argparse.Namespace)->None:
        self.args=args
        self.cli=CliChannel()
        self.agent_type=""
        self.product_root=""
        self.llm_provider,self.llm_model=self._load_default_model()
        self.session_by_key:dict[str,str]={}
        self.console=Console()
        self.notice=""

    def _load_default_model(self)->tuple[str,str]:
        try:
            provider,model=llm_factory.get_default_model()
            provider=(provider or "").strip() or "default"
            model=(model or "").strip() or "default"
            return provider,model
        except Exception:
            return "default","default"

    def _set_notice(self,text:str)->None:
        self.notice=(text or "").strip()

    def _build_inbound(self,content:str)->InboundMessage:
        prompt=content
        metadata={}
        if self.product_root:
            prompt=(
                f"[项目上下文]\n产品目录: {self.product_root}\n"
                f"[需求描述]\n{content}"
            )
            metadata["product_root"]=self.product_root
        return InboundMessage(
            channel_type=CLI_CHANNEL_TYPE,
            channel_id=CLI_CHANNEL_ID,
            user_id=CLI_USER_ID,
            session_id=self.cli.session_id or "",
            agent_type=self.agent_type,
            content=prompt,
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            metadata=metadata,
        )

    def _on_agent_message(self,text:str)->None:
        self._set_notice("Agent正在回复...")

    def _choose_from_list(self,title:str,choices:list[str],default_idx:int=0)->str:
        if not choices:
            raise ValueError(f"{title}选项为空。")
        while True:
            rows=[]
            for i,item in enumerate(choices, start=1):
                prefix="* " if i-1==default_idx else "  "
                rows.append(f"{prefix}{i}. {item}")
            self.console.print(Panel("\n".join(rows),title=title,expand=False))
            raw=input(f"{title}（输入编号，回车选默认 {default_idx+1}）> ").strip()
            if not raw:
                return choices[default_idx]
            if raw.isdigit():
                idx=int(raw)-1
                if 0<=idx<len(choices):
                    return choices[idx]
            print("输入无效，请输入列表中的编号。")

    def _default_agent_type(self)->str:
        if not AGENT_ROOT_PATH.exists():
            return "CodingAgent"
        agents=sorted([p.name for p in AGENT_ROOT_PATH.iterdir() if p.is_dir()])
        if not agents:
            return "CodingAgent"
        return agents[0]

    async def run(self)->None:
        await self.cli.startup()
        try:
            self.agent_type=self._default_agent_type()
            self._set_notice(
                f"欢迎使用 Pando Harness CLI | 模型: {self.llm_provider}/{self.llm_model}\n"
                "在主界面输入 /agent、/model、/project 可打开选择列表；/help 查看全部命令。"
            )
            await self._ensure_agent_session()
            while True:
                await self._render_layout()
                prompt=f"[{self.agent_type}|{self.llm_provider}/{self.llm_model}] 需求> "
                content=input(prompt).strip()
                if not content:
                    continue
                if content in {"/exit","exit","quit"}:
                    return
                if content in {"/help","help"}:
                    self._set_notice(
                        "支持命令:\n"
                        "/help 查看帮助\n"
                        "/agent 切换Agent（选择框）\n"
                        "/model 切换模型（选择框）\n"
                        "/project 切换产品目录（选择框）\n"
                        "/init 执行预处理(预留逻辑)\n"
                        "/exit|exit|quit 退出"
                    )
                    continue
                if content=="/agent":
                    self.agent_type=self._choose_agent_type()
                    if self._need_product_root() and not self.product_root:
                        self.product_root=self._prompt_product_root()
                    if not self._need_product_root():
                        self.product_root=""
                    await self._ensure_agent_session()
                    self._set_notice(f"已切换Agent: {self.agent_type}")
                    continue
                if content=="/model":
                    self.llm_provider,self.llm_model=self._choose_model()
                    self._set_notice(f"已切换模型: {self.llm_provider}/{self.llm_model}")
                    continue
                if content=="/init":
                    self._set_notice("预处理已触发（占位实现，后续可接入真实预处理服务）。")
                    continue
                if content=="/project":
                    if not self._need_product_root():
                        self._set_notice(f"当前Agent[{self.agent_type}]无需产品目录。")
                        continue
                    self.product_root=self._choose_product_root()
                    await self._ensure_agent_session()
                    self._set_notice(f"已切换产品目录: {self.product_root}")
                    continue
                if not self.cli.session_id:
                    await self._ensure_agent_session()
                if not self.cli.session_id:
                    if self._need_product_root() and not (self.product_root or "").strip():
                        self._set_notice("当前 Agent 需要产品目录，请在主界面执行 /project 选择目录后再输入需求。")
                    else:
                        self._set_notice("会话未就绪，请检查配置或稍后重试。")
                    continue
                await self.cli.send(inbound_msg=self._build_inbound(content),on_message=self._on_agent_message)
        finally:
            await self.cli.shutdown()

    def _choose_agent_type(self)->str:
        if not AGENT_ROOT_PATH.exists():
            agents=[]
        else:
            agents=sorted([p.name for p in AGENT_ROOT_PATH.iterdir() if p.is_dir()])
        if not agents:
            return self.agent_type or "CodingAgent"
        default_idx=agents.index(self.agent_type) if self.agent_type in agents else 0
        return self._choose_from_list("请选择Agent类型",agents,default_idx=default_idx).strip()

    def _choose_model(self)->tuple[str,str]:
        supported=llm_factory.get_supported_models().get("supported") or {}
        choices=[]
        for provider,pinfo in supported.items():
            for model in (pinfo.get("models") or {}).keys():
                choices.append(f"{provider}/{model}")
        if not choices:
            return self.llm_provider,self.llm_model
        current=f"{self.llm_provider}/{self.llm_model}"
        default=current if current in choices else choices[0]
        default_idx=choices.index(default) if default in choices else 0
        raw=self._choose_from_list("请选择模型",choices,default_idx=default_idx).strip()
        provider,model=raw.split("/",1)
        return provider.strip(),model.strip()     

    def _need_product_root(self)->bool:
        return self.agent_type not in AGENT_TYPES_WITHOUT_PROJECT_ROOT

    def _prompt_product_root(self)->str:
        while True:
            raw=input("请选择产品目录路径 > ").strip()
            if not raw:
                print("产品目录不能为空，请重新输入。")
                continue
            path=Path(raw).expanduser().resolve()
            if not path.exists() or not path.is_dir():
                print(f"目录不存在: {path}")
                continue
            return str(path)

    def _choose_product_root(self)->str:
        candidates=[]
        if self.product_root:
            candidates.append(self.product_root)
        cwd=Path.cwd()
        try:
            for p in sorted([d for d in cwd.iterdir() if d.is_dir()])[:20]:
                value=str(p.resolve())
                if value not in candidates:
                    candidates.append(value)
        except Exception:
            pass
        choices=candidates+["手动输入路径"]
        default_value=candidates[0] if candidates else "手动输入路径"
        default_idx=choices.index(default_value)
        value=self._choose_from_list("请选择产品目录",choices,default_idx=default_idx).strip()
        if not value:
            raise ValueError("未选择产品目录。")
        if value=="手动输入路径":
            return self._prompt_product_root()
        path=Path(value).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise ValueError(f"目录不存在: {path}")
        return str(path)

    async def _ensure_agent_session(self)->str:
        if self._need_product_root() and not (self.product_root or "").strip():
            self.cli.session_id=None
            return ""
        session_key=f"{self.agent_type}|{self.product_root}"
        existing=self.session_by_key.get(session_key)
        if existing:
            self.cli.session_id=existing
            return existing
        session_id=await SESSION_MANAGER.create_session(
            user_id=CLI_USER_ID,
            agent_type=self.agent_type,
            channel_type=CLI_CHANNEL_TYPE,
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            metadata={"product_root":self.product_root} if self.product_root else {},
        )
        self.cli.session_id=session_id
        self.session_by_key[session_key]=session_id
        self._set_notice(f"Agent[{self.agent_type}]会话已创建: {session_id}")
        return session_id
    
    async def _render_layout(self)->None:
        self.console.clear()
        sid=self.session_by_key.get(f"{self.agent_type}|{self.product_root}") or ""
        if sid:
            sess_short=sid if len(sid)<=24 else f"{sid[:21]}..."
        elif self._need_product_root() and not (self.product_root or "").strip():
            sess_short="未建立（需先 /project）"
        else:
            sess_short="未建立"
        header=(
            f"Pando Harness | Agent: {self.agent_type} | Model: {self.llm_provider}/{self.llm_model} "
            f"| Project: {self.product_root or '(无需)'} | Session: {sess_short}"
        )
        self.console.print(Panel(header,title="CLI",expand=False))
        if self.notice:
            self.console.print(Panel(self.notice,title="Notice",expand=False))
        lines=[]
        if sid:
            messages=await SESSION_MANAGER.get_messages(sid)
            for msg in messages[-30:]:
                data=msg.to_user_message()
                role=(data.get("role") or "").lower()
                text=(data.get("content") or "").strip()
                if not text:
                    continue
                if role=="user":
                    lines.append(f"[bold cyan]User:[/bold cyan] {text}")
                elif role=="assistant":
                    lines.append(f"[bold green]Agent:[/bold green] {text}")
                elif role=="tool":
                    lines.append(f"[bold magenta]Tool:[/bold magenta] {text}")
                else:
                    lines.append(f"[bold yellow]System:[/bold yellow] {text}")
        history_text="\n\n".join(lines) if lines else "[dim]暂无对话历史[/dim]"
        self.console.print(Panel(history_text,title="Conversation",expand=True))

def build_parser()->argparse.ArgumentParser:
    parser=argparse.ArgumentParser(description="Pando Harness CLI")
    parser.set_defaults(command="interactive")
    return parser
