# AiAssistant Agent Long-term Memory

## Core Capabilities
- Intelligent conversation and task execution assistant with code, file operations, search, and cron functionality
- Multilingual support (Chinese, English)
- Todo list management and status tracking
- Location-based services and navigation assistance

## Key Interaction Patterns
- When users write partial/unclear phrases, provide clarification options
- Respond in user's language when they communicate in that language
- For location/destination queries, require specific address or landmark details
- Use web_search for real-time information gathering (transportation, locations, services, price comparisons)
- Use todo_app for task management and todo_read for status checks
- Use status commands like /status? to check current task state

## Tool Usage Experience
- flight_search_flight requires departure, destination, and date parameters
- flight_search_flight returns structured data with airlines, times, and terminal information
- web_search requires query and optional count parameter for information gathering, effective for price comparisons across platforms
- todo_read for checking todo list status, returns remaining count and todo items
- cron reminders are system-internal notifications, not SMS/calls to external phone numbers
- Personal name tracking: remember and use user's preferred name in conversations

## Transportation Planning Essentials
- Xi'an to Shanghai: average travel time ~2.5 hours, China Eastern Airlines most popular
- Xi'an Airport: T3 for Shanghai flights, T5 for most other routes (not walkable)
- Shanghai airports: Hongqiao (closer to city), Pudong (international)
- Hongqiao Airport T2 directly connected to railway station (5-minute indoor walkway)
- Hongqiao Metro connections: Line 2 (downtown), Line 10 (city center), Line 17 (Xincen/Huawei R&D)
- Always include city-to-airport transit time (1-1.5 hours) and recommend arriving 2 hours before departure
- Tight schedule calculation: meeting time → airport arrival → flight departure → city departure

## Location-Specific Knowledge
- Shanghai Metro Line 17 serves Xincen Station (opened Nov 30, 2024) for Huawei R&D center
- Metro vs taxi: Metro cheaper and avoids traffic, taxi better for luggage
- Price comparison essential across platforms (Ctrip, Qunar, Fliggy, airline official sites)

## Flight Booking Process
- Airline websites and APPs provide direct booking, price protection, and 24/7 customer service
- Electronic invoice delivery via email, with customer service assistance available
- Airport counter service available for immediate paper invoices (require order number and ID)
- Multi-platform price comparison recommended: official sites, Ctrip, Qunar, Fliggy, Tianxun