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
- Use web_search for real-time information gathering (transportation, locations, services)
- Use todo_app for task management and todo_read for status checks
- Use status commands like /status? to check current task state

## Transportation & Planning Experience
- Flight Xi'an to Shanghai average travel time: ~2.5 hours
- Xi'an Airport Terminal T3 departure for Shanghai flights, Terminal T5 for most other routes
- Shanghai airports: Hongqiao (closer to city center), Pudong (international flights)
- Always check airport transit times and recommend arriving 2 hours before flight departure
- Include city-to-airport transit time in travel calculations (typically 1-1.5 hours)
- When users have tight schedules, calculate backwards: meeting time → airport arrival → flight departure → city departure timing
- Shanghai Hongqiao Airport to city center: Metro Line 10 (46 minutes, ~$1), Taxi (14 minutes, $11-14)
- Terminal distances matter - T3 and T5 at Xi'an airport are far apart and not walkable
- Shanghai Metro Line 17 serves West Qin Station for Huawei R&D center locations
- Hongqiao Airport transportation includes Line 2 (downtown), Line 10 (city center), and Line 17 (Xinqing/Huawei R&D)

## Tool Usage Experience
- flight_search_flight requires departure, destination, and date parameters
- flight_search_flight returns structured data with airlines, times, and terminal information
- web_search requires query and optional count parameter for information gathering
- todo_read for checking todo list status, returns remaining count and todo items
- Use web_search for location-based queries when specific addresses or landmarks are mentioned