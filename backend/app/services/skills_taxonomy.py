"""A built-in skills taxonomy + synonym normalization used by the job importer
(to extract skills from raw job postings) and the match engine (to compare a
career profile's skills against a job's required skills) without depending on
any external API.

This is intentionally a reasonably-sized, hand-curated list covering common
languages, frameworks/libraries, data/cloud/devops tools, and soft skills. It
is not exhaustive, but is broad enough for realistic tech-industry postings.
"""

from __future__ import annotations

import re

# Canonical skill name -> set of synonyms / alternate spellings (lowercased).
# The canonical name is what gets surfaced to users (matched_skills, etc).
SKILLS_TAXONOMY: dict[str, list[str]] = {
    # Languages
    "JavaScript": ["javascript", "js", "es6", "ecmascript"],
    "TypeScript": ["typescript", "ts"],
    "Python": ["python", "py"],
    "Java": ["java"],
    "C#": ["c#", "csharp", "c-sharp", ".net c#"],
    "C++": ["c++", "cpp"],
    "C": ["c programming", " c "],
    "Go": ["go", "golang"],
    "Rust": ["rust"],
    "Ruby": ["ruby"],
    "PHP": ["php"],
    "Swift": ["swift"],
    "Kotlin": ["kotlin"],
    "Scala": ["scala"],
    "R": ["r language", "r programming"],
    "SQL": ["sql", "t-sql", "pl/sql", "plsql"],
    "Bash": ["bash", "shell scripting", "shell"],

    # Frontend
    "React": ["react", "react.js", "reactjs"],
    "Next.js": ["next.js", "nextjs"],
    "Vue.js": ["vue", "vue.js", "vuejs"],
    "Angular": ["angular", "angularjs"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "Tailwind CSS": ["tailwind", "tailwindcss", "tailwind css"],
    "Redux": ["redux"],
    "Svelte": ["svelte"],

    # Backend / frameworks
    "Node.js": ["node", "node.js", "nodejs"],
    "Express.js": ["express", "express.js", "expressjs"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi", "fast api"],
    "Spring Boot": ["spring boot", "spring", "springboot", "spring-boot"],
    ".NET": [".net", "dotnet", "asp.net", "asp.net core", ".net core", ".net framework"],
    "Entity Framework": ["entity framework", "ef core", "entityframework", "efcore"],
    "Blazor": ["blazor"],
    "Xamarin": ["xamarin", "xamarin.forms", "xamarin forms"],
    ".NET MAUI": [".net maui", "dotnet maui", "maui"],
    "Javalin": ["javalin"],
    "Ruby on Rails": ["rails", "ruby on rails"],
    "GraphQL": ["graphql"],
    "REST APIs": [
        "rest api", "rest apis", "restful", "rest",
        "integracion de apis", "integración de apis", "api integration", "apis",
    ],
    "gRPC": ["grpc"],
    "Microservices": ["microservices", "microservice architecture"],

    # Data / ML
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning", "dl"],
    "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "Data Analysis": ["data analysis", "data analytics"],
    "ETL": ["etl", "extract transform load"],
    "Apache Spark": ["spark", "apache spark", "pyspark"],
    "Airflow": ["airflow", "apache airflow"],

    # Databases
    "PostgreSQL": ["postgresql", "postgres", "psql"],
    "SQL Server": ["sql server", "mssql", "microsoft sql server", "ms sql", "ms sql server"],
    "MySQL": ["mysql"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic search"],
    "SQLite": ["sqlite"],
    "DynamoDB": ["dynamodb"],
    "Cassandra": ["cassandra"],

    # Cloud / DevOps
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure", "microsoft azure"],
    "Google Cloud Platform": ["gcp", "google cloud", "google cloud platform"],
    "Docker": ["docker", "containerization", "docker compose", "docker-compose", "dockerfile"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Terraform": ["terraform", "iac", "infrastructure as code"],
    "CI/CD": ["ci/cd", "cicd", "continuous integration", "continuous deployment"],
    "Jenkins": ["jenkins"],
    "GitHub Actions": ["github actions"],
    "Linux": ["linux", "unix"],
    "Nginx": ["nginx"],
    "Ansible": ["ansible"],

    # Tools / practices
    "Git": ["git", "version control"],
    "Agile": ["agile", "scrum", "kanban"],
    "Jira": ["jira"],
    "Testing": ["unit testing", "test automation", "tdd", "qa", "quality assurance"],
    "System Design": ["system design", "distributed systems"],
    "API Design": ["api design"],
    "Message Queues": ["kafka", "rabbitmq", "message queue", "message queues", "sqs"],

    # Soft skills
    "Leadership": ["leadership", "team lead", "liderazgo"],
    "Communication": ["communication", "comunicación", "comunicacion"],
    "Problem Solving": ["problem solving", "resolución de problemas"],
    "Project Management": ["project management", "gestión de proyectos"],
    "Mentoring": ["mentoring", "mentorship"],
    "Collaboration": ["collaboration", "teamwork", "trabajo en equipo"],
}

#: The soft-skill block above, named so the match engine can tell "this
#: posting asks for Communication" from "this posting asks for Python".
#: Every posting asks for communication; matching on it says nothing about
#: technical fit, and a posting whose *only* parsed requirements are these
#: scored a perfect technical 100 (see match_engine.compute_technical_score).
SOFT_SKILLS: frozenset[str] = frozenset(
    {
        "Leadership",
        "Communication",
        "Problem Solving",
        "Project Management",
        "Mentoring",
        "Collaboration",
    }
)

# Flat lookup: normalized synonym string -> canonical skill name.
_SYNONYM_TO_CANONICAL: dict[str, str] = {}
for _canonical, _synonyms in SKILLS_TAXONOMY.items():
    _SYNONYM_TO_CANONICAL[_canonical.strip().lower()] = _canonical
    for _syn in _synonyms:
        _SYNONYM_TO_CANONICAL[_syn.strip().lower()] = _canonical

# Sorted longest-first so multi-word synonyms (e.g. "ruby on rails") are matched
# before shorter substrings (e.g. "ruby") during free-text scanning.
_ALL_SYNONYMS_SORTED = sorted(_SYNONYM_TO_CANONICAL.keys(), key=len, reverse=True)


def normalize_skill(raw: str) -> str:
    """Map a raw skill string to its canonical taxonomy name, or return the
    trimmed original (title-cased) if it's not recognized."""
    key = raw.strip().lower()
    if key in _SYNONYM_TO_CANONICAL:
        return _SYNONYM_TO_CANONICAL[key]
    return raw.strip()


#: Spellings that must never match on their own. Every canonical name is
#: also registered as its own synonym (see the loop above), so these ordinary
#: English words — and two single letters — fired on prose. Measured on this
#: database: "Go" was a required skill on 46 of 196 postings, "REST APIs" on
#: 48 and "C" on 54, the last mostly from "C++"/"C#", since the boundary
#: guard treats "+" and "#" as separators. This sentence, with nothing
#: technical in it, extracted five skills: "The rest of the team will go to
#: the spring offsite."
#: The longer spellings still match ("golang", "rest api", "spring boot",
#: "c programming"), so a posting that really asks for them keeps them.
#: "react" and "swift" stay matchable: unlike these, that is how postings
#: normally write the technology, and losing them costs more than the
#: occasional "react to feedback".
#: Las siglas de dos letras se anadieron despues, por el mismo motivo y con
#: el mismo criterio: "Trabajamos con ML y DL" es tecnico, pero "el equipo de
#: TS revisa los tickets" y "reunion el proximo dl" no lo son, y el CV subido
#: pasa por este mismo escaner, asi que inventaba habilidades en el borrador
#: del perfil. Las formas largas siguen detectandose ("machine learning",
#: "deep learning", "typescript"), que es como las escriben las ofertas.
NEVER_MATCH_BARE: frozenset[str] = frozenset(
    {"go", "rest", "spring", "c", "r", "ml", "dl", "ts"}
)


def extract_skills_from_text(text: str) -> list[str]:
    """Scan free text for occurrences of any taxonomy skill/synonym and return
    the deduplicated list of canonical skill names found, in order of first
    appearance."""
    if not text:
        return []
    lowered = f" {text.lower()} "
    found: list[str] = []
    seen: set[str] = set()
    for synonym in _ALL_SYNONYMS_SORTED:
        if synonym in NEVER_MATCH_BARE:
            continue
        canonical = _SYNONYM_TO_CANONICAL[synonym]
        if canonical in seen:
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(synonym) + r"(?![a-z0-9])"
        if re.search(pattern, lowered):
            found.append(canonical)
            seen.add(canonical)
    return found


def canonical_skill_set(skill_names: list[str]) -> set[str]:
    return {normalize_skill(s) for s in skill_names if s}
