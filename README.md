#  Development Journal

**Day 1 — The Idea**

The project started with a simple question:

What if a student had a personal AI assistant that could actually help manage the entire study process?

Instead of creating a normal chatbot, I wanted to build something that could:

Understand questions
Explain concepts
Calculate answers
Generate quizzes
Create study plans
Remember useful information
Read documents
Search knowledge
Work with notes

The first major decision was to build SAGE as an AI Agent rather than a normal question-answering application.

What I learned
Difference between a chatbot and an AI Agent
How LLMs can interact with external tools
Basic AI Agent architecture
Why tool calling is important


**Day 2 — Designing the Agent**

The next step was designing the internal architecture.

I divided the Agent into several components:

Agent
│
├── Planner
├── Tool Registry
├── Tool Executor
├── LLM Client
├── Memory
├── RAG
└── System Prompt

The idea was to give each component a specific responsibility.

Planner

Responsible for understanding what needs to be done.

Tool Registry

Keeps track of the tools available to SAGE.

Tool Executor

Actually executes the selected tool.

LLM Client

Handles communication with the language model.

Memory

Stores relevant conversation and long-term information.

RAG

Allows SAGE to work with uploaded knowledge.

What I learned

I learned that a good AI Agent is not just an LLM.

The LLM is the brain, but the Agent architecture provides the ability to interact with the outside world.

**Day 3 — Connecting the LLM**

I connected SAGE to an LLM through OpenRouter.

The application uses an OpenAI-compatible interface so that the backend can communicate with supported models without tightly coupling the application to a single provider.

The basic flow became:

User Question
      ↓
SAGE Agent
      ↓
LLM
      ↓
Response

At this stage SAGE could already answer normal questions.

For example:

User:
What is normalization in DBMS?

SAGE:
Normalization is the process of organizing data...
What I learned
How API-based LLM communication works
Environment variables
API key security
System prompts
Chat messages
LLM responses

**Day 4 — Building the Tool System**

A major improvement came when I started adding tools.

Instead of asking the LLM to perform everything itself, SAGE could now decide when a tool was required.

Tools included:

Calculator
Date/time
Notes
Marks
Study planner
Quiz generator
Web search
PDF reader
Code analyzer
CSV analysis
Memory
Reminders
Calendar

The architecture became:

User
 ↓
LLM
 ↓
"Do I need a tool?"
 ↓
YES
 ↓
Tool Registry
 ↓
Tool Executor
 ↓
Tool Result
 ↓
LLM
 ↓
Final Answer
What I learned

This was one of the most important concepts in the project:

The LLM does not need to know how to perform every operation. It needs to know when an operation should be delegated to a tool.

**Day 5 — Building the Agent Loop**

A simple chatbot normally works like:

Question → LLM → Answer

SAGE needed something more powerful.

I implemented an agent loop:

User
 ↓
LLM
 ↓
Decision
 ↓
Tool Call
 ↓
Tool Result
 ↓
LLM
 ↓
Another Decision
 ↓
Another Tool
 ↓
Final Answer

This allows SAGE to perform multi-step tasks.

For example:

User:
Calculate my average marks and tell me whether I need to improve.

SAGE
 ↓
Retrieve marks
 ↓
Calculate average
 ↓
Analyze result
 ↓
Generate explanation
What I learned
Multi-step reasoning architecture
Tool execution loops
Tool results
Iteration limits
Error handling

**Day 6 — Memory**

The next challenge was making SAGE remember useful information.

I separated memory into:

Short-Term Memory

Used for the current conversation.

User:
Explain 2NF.

SAGE:
...

User:
Now explain 3NF.

SAGE:
...

SAGE can understand that "now" refers to the current conversation.

Long-Term Memory

Used for useful information that should remain available.

For example:

User prefers simple explanations.

or

User is preparing for DBMS examinations.

The memory system became:

SAGE
 │
 ├── Short-Term Memory
 │
 └── Long-Term Memory
What I learned

Memory is different from simply storing chat messages.

The system must distinguish between:

Conversation history
Useful persistent information
Temporary context

**Day 7 — Database**

SQLite was selected because SAGE is currently a personal single-user application.

The database stores information such as:

Notes
Marks
Study plans
Memories
Reminders
Calendar events
Conversations
Messages

The goal was to keep the architecture lightweight while still providing persistent storage.

What I learned
SQLAlchemy
Database models
CRUD operations
Database sessions
Persistent application state

**Day 8 — RAG**

One of the most important features was adding document understanding.

The problem was:

General LLM knowledge is not always enough for a student's specific syllabus or uploaded material.

So I implemented Retrieval-Augmented Generation.

The process became:

PDF / Document
      ↓
Text Extraction
      ↓
Chunking
      ↓
Embeddings
      ↓
Vector Store
      ↓
Similarity Search
      ↓
Relevant Context
      ↓
LLM
      ↓
Answer

Now a student can provide study material and ask SAGE questions about it.

Example
User:
Explain deadlock using my uploaded OS notes.

SAGE
 ↓
Search uploaded notes
 ↓
Retrieve relevant section
 ↓
Send context to LLM
 ↓
Explain in simple language
What I learned
Embeddings
Semantic search
Chunking
Vector retrieval
RAG architecture
Difference between general knowledge and retrieved knowledge

**Day 9 — Student-Focused Intelligence**

The next step was making SAGE specifically useful for students.

Instead of simply answering questions, SAGE was designed to understand common student requirements.

Examples:

"Explain this simply."

"Give me a 5-mark answer."

"Give an example."

"Quiz me on this."

"Make a study plan."

"Summarize these notes."

"Compare these two concepts."

"Explain this like I'm a beginner."

The system prompt was improved to encourage:

Clear explanations
Examples
Structured answers
Appropriate academic depth
Student-friendly language
What I learned

A good AI application is not only about the model.

Prompt design + context + tools + application logic strongly affect the final experience.

**Day 10 — FastAPI Backend**

I built the backend using FastAPI.

The backend became the communication layer between the frontend and SAGE Agent.

The main flow became:

Frontend
   ↓
POST /api/chat
   ↓
FastAPI
   ↓
SAGE Agent
   ↓
LLM / Tools / Memory / RAG
   ↓
FastAPI
   ↓
Frontend

FastAPI also provided automatic API documentation.

The backend could be accessed through:

http://127.0.0.1:8000

and the API documentation through:

http://127.0.0.1:8000/docs
What I learned
FastAPI routing
Request/response schemas
Dependency injection
API design
Uvicorn
Backend testing

**Day 11 — Debugging the Backend**

While testing the backend, I encountered dependency and environment issues.

One major issue was:

ModuleNotFoundError:
No module named 'sentence_transformers'

Another was:

ModuleNotFoundError:
No module named 'bs4'

I learned that having a package listed in requirements.txt does not automatically mean it is installed in the Python environment currently running the application.

I also learned the importance of checking which Python executable is being used.

The backend was eventually brought to a working state.

What I learned
Python virtual environments
pip
requirements.txt
Module installation
Python interpreter selection
Reading traceback errors
Debugging FastAPI applications

**Day 12 — Designing the SAGE Interface**

After the backend became stable, I started designing the frontend.

The interface was designed around a clean study-focused experience.

The main design colors are:

Green  → #598556
Beige  → #EDE8D0

The interface contains:

SAGE branding
Sidebar navigation
Chat interface
Conversation history
New Chat
Templates
Notes
Study Plan
Uploads
Memory
Settings
Light/Dark mode

The goal was to avoid the typical "cyberpunk AI" appearance and instead create something calm and suitable for studying.

**Day 13 — SAGE Branding**

The assistant was given the name:

SAGE

Your AI Study Assistant

The interface was designed around the SAGE identity.

The logo is used throughout the application:

Sidebar
Assistant messages
Welcome screen
Chat interface

The light and dark themes use inverted logo colors.

Light Mode
Green → #598556
Beige → #EDE8D0
Dark Mode

The visual relationship is inverted while maintaining the SAGE identity.

**Day 14 — Building the Chat Interface**

The chat interface was connected to the FastAPI backend.

The frontend sends:

User Message
 ↓
FastAPI
 ↓
SAGE Agent

and receives:

SAGE Response

The interface displays:

User messages
SAGE messages
Loading states
Timestamps
Chat bubbles
Input composer

SAGE responses are designed to support Markdown formatting.

This means responses such as:

## Normalization

Normalization is the process of organizing data.

- 1NF
- 2NF
- 3NF
- BCNF

can be rendered as properly formatted content in the UI.

**Day 15 — Multi-Conversation History**

A major requirement was making SAGE capable of maintaining multiple conversations.

Instead of one continuous chat, conversations are stored separately.

The structure is:

Conversation 1
 ├── Message
 ├── Message
 └── Message

Conversation 2
 ├── Message
 ├── Message
 └── Message

Conversation 3
 ├── Message
 └── Message

This allows the user to:

Start a new chat
Continue an old chat
Switch between conversations
Delete conversations
Preserve previous messages

This makes the application behave more like a real AI assistant rather than a temporary demo.



**Day 16 — Connecting the Workspace**

The next stage was turning the visual navigation into real functionality.

The SAGE workspace contains:

Explore
Templates
Notes
Study Plan
Uploads
Memory

Each section is designed to communicate with the existing backend.

Templates

Provides ready-made study prompts.

Notes

Connects to the notes database/tools.

Study Plan

Connects to the study planning system.

Uploads

Connects to document processing and RAG.

Memory

Connects to the long-term memory system.

This ensures that the frontend does not contain fake placeholder functionality.

**Day 17 — Frontend + Agent Integration**

The complete application architecture now becomes:

                         USER
                           │
                           ▼
                    ┌────────────┐
                    │    SAGE    │
                    │  Frontend  │
                    └──────┬─────┘
                           │
                           ▼
                    ┌────────────┐
                    │  FastAPI   │
                    └──────┬─────┘
                           │
                           ▼
                    ┌────────────┐
                    │ SAGE Agent │
                    └──────┬─────┘
                           │
             ┌─────────────┼─────────────┐
             │             │             │
             ▼             ▼             ▼
            LLM          Tools        Memory
             │             │             │
             │      ┌──────┼──────┐      │
             │      │      │      │      │
             ▼      ▼      ▼      ▼      ▼
           Answer  Notes  Quiz  Plans   Context
                       │
                       ▼
                      RAG
                       │
                       ▼
                 Uploaded Files

The frontend becomes the interface.

The Agent remains the intelligence layer.

**Day 18 — Making SAGE a Real Personal Assistant**

The final goal is not simply:

"Build a chatbot."

The goal is:

Build a personal AI study environment.

SAGE should allow a student to move naturally between:

Ask
 ↓
Understand
 ↓
Practice
 ↓
Plan
 ↓
Store
 ↓
Review
 ↓
Improve

For example:

User:
I have an OS exam in 7 days.

SAGE:
Creates a study plan.

↓

User:
Explain semaphores.

SAGE:
Explains the concept.

↓

User:
Give me a 5-mark answer.

SAGE:
Formats the answer for examination.

↓

User:
Quiz me.

SAGE:
Generates questions.

↓

User:
Save this topic to my notes.

SAGE:
Stores the note.

↓

User:
Remind me tomorrow.

SAGE:
Creates a reminder.

This is the point where SAGE becomes more than a chatbot.