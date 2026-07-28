"""Punto único de importación de todos los modelos.

Existe por dos razones prácticas:

1. Alembic necesita que **todas** las tablas estén registradas en `SQLModel.metadata`
   antes de autogenerar una migración. Si un módulo no se importa, su tabla se detecta
   como "borrada" y la migración generada intenta hacer DROP TABLE.
2. Los modelos usan claves ajenas por nombre de tabla en string (`"users.id"`), que
   SQLAlchemy resuelve al configurar los mappers. Importarlos todos juntos garantiza que
   la resolución no dependa del orden en que los toque el resto de la aplicación.

**Regla del proyecto: todo punto de entrada que toque la base de datos importa este módulo.**
Eso incluye `app/main.py`, `app/workers/celery_app.py` y cualquier script de `scripts/`.
Importar solo los modelos que usa un fichero concreto parece funcionar hasta que se hace el
primer commit de una entidad con clave ajena hacia otro módulo, y entonces falla con
`NoReferencedTableError: Foreign key ... could not find table 'machine_models'`.
"""

from app.modules.agent.models import (
    AgentConfig,
    Conversation,
    DocumentSourceType,
    IngestStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    LLMProviderKey,
    Message,
    MessageRole,
    ProviderCredential,
    ToolAuthType,
    ToolDefinition,
    ToolInvocation,
)
from app.modules.assessments.models import (
    AnswerOption,
    AttemptAnswer,
    Certificate,
    Question,
    QuestionType,
    Quiz,
    QuizAttempt,
)
from app.modules.auth.models import User, UserRole
from app.modules.lms.models import (
    Lesson,
    LessonContentType,
    ProgressStatus,
    TrainingModule,
    UserLessonProgress,
    VideoAsset,
    VideoStatus,
)
from app.modules.machines.models import MachineModel, PublishStatus, Specialty

# Agrupado por módulo y no alfabéticamente a propósito: así se lee de un vistazo qué entidades
# aporta cada feature, que es justo la información útil en este fichero. De ahí el `noqa`.
__all__ = [  # noqa: RUF022
    # auth
    "User",
    "UserRole",
    # machines
    "MachineModel",
    "PublishStatus",
    "Specialty",
    # lms
    "TrainingModule",
    "Lesson",
    "LessonContentType",
    "VideoAsset",
    "VideoStatus",
    "UserLessonProgress",
    "ProgressStatus",
    # assessments
    "Quiz",
    "Question",
    "QuestionType",
    "AnswerOption",
    "QuizAttempt",
    "AttemptAnswer",
    "Certificate",
    # agent
    "ProviderCredential",
    "LLMProviderKey",
    "AgentConfig",
    "KnowledgeDocument",
    "KnowledgeChunk",
    "DocumentSourceType",
    "IngestStatus",
    "ToolDefinition",
    "ToolAuthType",
    "ToolInvocation",
    "Conversation",
    "Message",
    "MessageRole",
]
