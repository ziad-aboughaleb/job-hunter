from typing import Any

from pydantic import BaseModel, Field
from pydantic.aliases import AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import CONFIG_PATH, get_project_root, read


class ProfileConfig(BaseModel):
  target_roles: str = ""


class FiltersConfig(BaseModel):
  title_include: list[str] = []
  title_exclude: list[str] = []
  stack_keywords: list[str] = []
  min_stack_hits: int = 0
  company_exclude: list[str] = []
  company_priority: list[str] = []
  require_remote: bool = True
  remote_keywords: list[str] = ["remote", "wfh", "work from home", "anywhere", "telecommute", "fully remote", "100% remote"]
  location_exclude_terms: list[str] = ["us only", "us-only", "united states only", "canada only", "uk only", "must reside in"]
  location_allow_terms: list[str] = []
  location_require_terms: list[str] = []
  max_age_days: int = 14


class LimitsConfig(BaseModel):
  max_candidates_per_run: int = 30
  description_max_chars: int = 7000
  seen_retention_days: int = 90
  fetch_workers: int = 8


class ScoringWeight(BaseModel):
  name: str
  weight: int
  what: str


class EvaluatingConfig(BaseModel):
  score_threshold: int = 65
  scoring_weights: list[ScoringWeight] = Field(default_factory=list)


class LLMConfig(BaseModel):
  provider: str = "openai"
  base_url: str | None = None
  model: str | None = None
  request_delay: int = 5
  max_workers: int = 1
  temperature: float = 0.0
  timeout: int = 600


class TelegramConfig(BaseModel):
  link_preview: bool = False
  notify_on_empty: bool = True


class Settings(BaseSettings):
  telegram_bot_token: str = Field(default="", validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "telegram_bot_token"))
  telegram_chat_id: str = Field(default="", validation_alias=AliasChoices("TELEGRAM_CHAT_ID", "telegram_chat_id"))
  llm_api_key: str = Field(default="", validation_alias=AliasChoices("LLM_API_KEY", "llm_api_key"))

  profile: ProfileConfig = Field(default_factory=ProfileConfig)
  boards: dict[str, Any] = Field(default_factory=dict)
  companies: dict[str, list[str]] = Field(default_factory=dict)
  filters: FiltersConfig = Field(default_factory=FiltersConfig)
  limits: LimitsConfig = Field(default_factory=LimitsConfig)
  evaluating: EvaluatingConfig = Field(default_factory=EvaluatingConfig)
  llm: LLMConfig = Field(default_factory=LLMConfig)
  telegram: TelegramConfig = Field(default_factory=TelegramConfig)

  cv_text: str = ""
  preferences_text: str = ""

  model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def load_settings() -> Settings:
  """Loads settings from JSON and Markdown files, returning a Settings object."""
  config_dir = get_project_root() / "config"

  # Load JSON
  config_data = read(CONFIG_PATH / "config.json", dict)

  # Remove "_help"
  config_data.pop("_help", None)

  # Load Markdown
  cv_path = config_dir / "cv.md"
  pref_path = config_dir / "preferences.md"

  return Settings(
    cv_text=cv_path.read_text(encoding="utf-8") if cv_path.exists() else "",
    preferences_text=pref_path.read_text(encoding="utf-8") if pref_path.exists() else "",
    **config_data,
  )


settings = load_settings()




{
  "profile": {
    "target_roles": "full-stack or frontend/backend JavaScript and TypeScript web development"
  },
  "boards": {
    "remotive": {
      "enabled": true,
      "category": "software-dev"
    }
  },
  "companies": {
    "personio": [
      "athereon",
      "bookboost",
      "carbmee",
      "chrono24",
      "cyens-centre-of-excellence",
      "edri",
      "evidentiq",
      "fact-finder",
      "graswald-gmbh",
      "impower",
      "jobleads",
      "journaway-gmbh",
      "knime",
      "koppla",
      "liveeo-gmbh",
      "merantix",
      "mercanis",
      "metycle",
      "mway",
      "native-design",
      "newboxes",
      "next-mobility-labs",
      "oh-so",
      "oivan-group-oy",
      "ommax",
      "othermo",
      "prenode",
      "pro4all",
      "saltocloudworks",
      "snke",
      "tonies",
      "traide-ai",
      "transitionzero",
      "trever",
      "twaice",
      "twentyfour-industries",
      "ytec"
    ],
    "greenhouse": [
      "2k",
      "affirm",
      "alpaca",
      "anthropic",
      "arcesiumllc",
      "assetliving",
      "autoproff",
      "builder",
      "capco",
      "clara",
      "coconutsoftware",
      "cssmerge",
      "d3",
      "deliveroo",
      "doordashusa",
      "doubleverify",
      "easygo",
      "emergentlabsinc",
      "enterpret",
      "figma",
      "fueledcareers",
      "future",
      "gitlab",
      "gleanwork",
      "globalwebindex",
      "gomotive",
      "headoutcareers",
      "heygen",
      "incode",
      "instalilyai",
      "isaac",
      "machinifyinc",
      "oddball",
      "onxmaps",
      "otter",
      "oura",
      "projectaservicesgmbhcokg",
      "rackner",
      "reddit",
      "relativity",
      "roadie",
      "singlestore",
      "spotter",
      "stackav",
      "staffbase",
      "tastytrade",
      "tecovas",
      "tia",
      "trueanomalyinc",
      "verkada",
      "workatbackbase",
      "xai",
      "xpinc",
      "zupinnovation"
    ],
    "lever": [
      "curai",
      "drivetrain",
      "firstup",
      "hive",
      "jobgether",
      "kpler",
      "lyrahealth",
      "mable",
      "merklescience",
      "netomi",
      "palantir",
      "revealtech",
      "spotify",
      "supermove",
      "venusaero",
      "viome",
      "virtualitics",
      "xsolla"
    ],
    "recruitee": [
      "aikidosecurity",
      "appetiser",
      "axual",
      "ballysintralotsa",
      "box8",
      "careersdeltacapita",
      "craftzing",
      "curotec",
      "distilled",
      "easyapplyrekluti",
      "epilot",
      "grid",
      "hubvisory",
      "kdci1",
      "litit",
      "make",
      "nodeworthy",
      "oscalabv",
      "qualifyzegmbh",
      "resourcefultalentgroup",
      "trafilea",
      "transperfect"
    ],
    "workable": [
      "advansys-esc-1",
      "ajaia",
      "alten-mexico-1",
      "arondite",
      "bask-health-1",
      "brightorder",
      "bystadium",
      "codeninjapk",
      "crazymaplestudio",
      "gathern",
      "hellogov",
      "huzzle",
      "hyprwork",
      "lucidya",
      "matternet",
      "maxana",
      "modash",
      "opendatajobs",
      "openfn",
      "optiplay-io",
      "origin-10x",
      "robusta",
      "sideinc",
      "ssc-hr",
      "stackbuilders",
      "transform9",
      "velsera",
      "webook",
      "writesonic"
    ]
  },
  "filters": {
    "title_include": [
      "full-stack",
      "fullstack",
      "full stack",
      "frontend",
      "front-end",
      "backend",
      "back-end",
      "react",
      "next.js",
      "nextjs",
      "node.js",
      "nodejs",
      "web developer",
      "javascript",
      "typescript",
      "software engineer",
      "web engineer",
      "junior",
      "entry level",
      "entry-level",
      "associate",
      "trainee",
      "intern",
      "internship",
      "graduate",
      "early career"
    ],
    "title_exclude": [
      "recruiter",
      "sales",
      "marketing",
      "account executive",
      "customer success",
      "designer",
      "devops",
      "sre",
      "data engineer",
      "data scientist",
      "machine learning",
      "qa",
      "sdet",
      "android",
      "ios",
      "mobile",
      "embedded",
      "firmware",
      "hardware",
      "java",
      "golang",
      "php",
      "ruby",
      "c#",
      "c++",
      ".net",
      "angular",
      "vue",
      "svelte",
      "salesforce",
      "wordpress",
      "director",
      "vp",
      "vice president",
      "head of",
      "principal",
      "staff",
      "lead",
      "senior",
      "sr",
      "mid-senior",
      "iii",
      "iv",
      "architect",
      "manager"
    ],
    "stack_keywords": [
      "react",
      "next.js",
      "nextjs",
      "typescript",
      "javascript",
      "node",
      "nodejs",
      "express",
      "mongodb",
      "mongoose",
      "redux",
      "rtk query",
      "tanstack",
      "tailwind",
      "vite",
      "redis",
      "nestjs",
      "nest.js",
      "postgresql",
      "prisma",
      "graphql",
      "websockets",
      "ci/cd",
      "turborepo",
      "docker",
      "stripe"
    ],
    "min_stack_hits": 2,
    "company_exclude": [],
    "company_priority": [],
    "require_remote": true,
    "location_exclude_terms": [
      "us only",
      "us-only",
      "united states only",
      "canada only",
      "uk only",
      "must reside in"
    ],
    "location_allow_terms": [],
    "location_require_terms": [],
    "max_age_days": 14
  },
  "limits": {
    "max_candidates_per_run": 30,
    "description_max_chars": 7000,
    "seen_retention_days": 90,
    "fetch_workers": 8
  },
  "evaluating": {
    "score_threshold": 65,
    "scoring_weights": [
      {
        "name": "Core skills overlap",
        "weight": 50,
        "what": "required technologies and skills that the CV demonstrates"
      },
      {
        "name": "Experience and seniority fit",
        "weight": 20,
        "what": "years and level compared with cv and prefrences"
      },
      {
        "name": "Role type and location fit",
        "weight": 20,
        "what": "title fit, and a work arrangement and location that suit the candidate"
      },
      {
        "name": "Nice-to-haves",
        "weight": 10,
        "what": "secondary tools, methodologies and soft skills"
      }
    ]
  },
  "llm": {
    "provider": "openai",
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    "model": "gemini-3.5-flash-lite",
    "request_delay": 5,
    "max_workers": 1
  },
  "telegram": {
    "link_preview": false,
    "notify_on_empty": true
  }
}



Ziad Aboughaleb
Cairo, Egypt | +20 150 888 7499 | ziadaboughaleb@gmail.com
ziad-aboughaleb.vercel.app | linkedin.com/in/ziad-aboughaleb | github.com/ziad-aboughaleb
Summary
Full-Stack Web Developer specializing in the MERN stack, Next.js, and TypeScript. Experienced in building scalable
e-commerce platforms with modular REST APIs, secure authentication workflows, and responsive admin dashboards.
Education
Faculty of Electronic Engineering, Menoufia University
Oct 2023 – Expected Oct 2028
B.Sc. Electrical, Electronics, and Communications Engineering
Egypt
- Relevant Coursework: Data Structures & Algorithms, Digital Logic, Computer Networks, Linear Algebra,

Probability & Statistics
SEF Academy
Nov 2025 – Sep 2026
Full-Stack Web Development Program
Remote
- Completed front-end, back-end, and full-stack tracks scoring 98.92%, 98.78%, and 98.85% respectively

Experience
SEF Academy
Aug 2026 – Sep 2026
Back-End Web Development Trainee | GitHub | API Docs
Remote
- Collaborated with a development team to build a production-style e-commerce REST API using Node.js,

Express.js, MongoDB, Mongoose, and Redis
- Owned the core authentication flow, implementing JWT access tokens, refresh tokens stored in HTTP-only

cookies, OTP email verification, password handling, request validation and role-based authorization
- Implemented Redis caching for frequently accessed product and catalog data, reducing database query load and

improving overall API response times
- Contributed to a documented API with 40+ documented REST operations covering authentication, products,

carts, wishlists, orders, users, and admin analytics
- Integrated Cloudinary image uploads and Stripe, PayPal, and Paymob payment workflows, including payment

webhooks
- Used Git and GitHub in a collaborative workflow involving feature development, code review, and integration

SEF Academy
Jul 2026 – Aug 2026
Front-End Web Development Trainee | GitHub | Live Demo
Remote
- Collaborated in a team-based development environment to build a scalable Turborepo monorepo

e-commerce platform using React, Vite, TypeScript, Tailwind CSS, and TanStack Query
- Contributed to the customer storefront and admin dashboard, implementing authentication, product

management, shopping cart functionality, and Stripe checkout
- Used Git and GitHub in a collaborative development workflow to contribute features and integrate work across

the team
Technical Skills
Languages: HTML, CSS, JavaScript, TypeScript, Python
Front-End: React, Next.js, Vite, Tailwind CSS, Redux Toolkit, RTK Query, TanStack Query/Form
Back-End: Node.js, Express.js, MongoDB, Mongoose, REST APIs, JWT, Redis
CS Foundations: Data Structures & Algorithms, Computer Networks, Digital Logic
Tools: Git, GitHub, GitHub Actions, npm Workspaces, Docker, Unix/Linux, Turborepo, Vercel, Vitest
Integrations: LLM APIs (OpenAI/Gemini), Telegram API, Stripe, PayPal, Cloudinary, EmailJS
Familiar With: Nest.js, PostgreSQL, Prisma, GraphQL, WebSockets, CI/CDProjects
AI-Powered Job Hunter Pipeline
Oct 2026
Python, LLM APIs (Gemini/OpenAI), Telegram API, GitHub Actions
GitHub
- Engineered a zero-dependency Python pipeline that aggregates remote tech jobs and scores them using LLMs based

on custom candidate CVs and preference rules.
- Designed a decoupled 3-stage architecture (fetch, evaluate, send) triggered daily via GitHub Actions, passing state

through JSON files to ensure fault tolerance.
- Integrated Telegram’s API to automatically deliver highly-rated job matches with custom AI-generated pitch lines

directly to mobile.
Next.js E-Commerce Platform
May 2026 – Jun 2026
Next.js, React, TypeScript, Redux Toolkit, RTK Query, Tailwind CSS
GitHub | Live Demo
- Built a modern e-commerce application featuring product search, filtering, pagination, product details, responsive

layouts, and dynamic API-driven content
- Implemented persistent cart and wishlist state with Redux Persist and integrated the DummyJSON REST

API through RTK Query
Personal Portfolio Website
Apr 2026
GitHub | Live Demo
Next.js, TypeScript, GitHub API, Microlink API, EmailJS, TanStack Form
- Built a responsive portfolio using Next.js and TypeScript, integrating the GitHub API and Microlink API

for dynamic project content
- Developed a contact system with EmailJS and TanStack Form, adding validation, notifications, theme

persistence, and performance optimizations



# Job preferences (edit me - the evaluator reads this file)

## Target roles

- Frontend Developer, Full-Stack Developer, Web Developer, React Developer, Node.js Developer


## Seniority

- My total years of formal experience: 0-1 (Entry-level / Junior / Fresh Graduate)


- Levels I accept: Entry-level, Junior, Associate, Mid-level, and postings requesting 1–3 years of experience.


- DO NOT hard fail roles requiring 2+ or 3+ years of experience. Treat my production-style traineeship and full-stack project experience as equivalent practical experience.


- Hard fail ONLY if the posting strictly requires 4 or more years of experience, or is explicitly Senior, Staff, Principal, Lead, or Management level.


## Location and eligibility (HARD GATE)

- I can work remotely from: Egypt (EMEA region)


- Time zone I can overlap with: UTC+0 to UTC+4 (Europe, Middle East, Africa, and flexible Worldwide roles)


- Reject (hard fail) if the posting restricts candidates to a country/region I am not in (e.g. "must reside in the US/Canada", "US work authorization required", "LATAM only").


- Open to contractor / employer-of-record arrangements: Yes


## Dealbreakers (HARD FAIL)

- Requires on-site or hybrid presence (must be 100% remote)

- Requires active US/EU security clearance or specific local work visas

- Requires languages other than English or Arabic


## Nice to have (bonus only, never a requirement)

- Next.js and TypeScript-heavy codebases

- MERN stack or modern Node.js/Redis backends

- Internships or entry-level friendly programs

- Global/Worldwide remote teams
