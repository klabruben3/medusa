from typing import List, Optional, Literal, Tuple, TypedDict
from pydantic import BaseModel, Field

AssessmentType = Literal[
    "weekly-test", "class-test", "semester-test", "exam", "assignment",
    "online-test", "attendance", "aleks", "class-work", "practical",
    "practical-exam", "mcq",
]

class AssessmentSlot(BaseModel):
    date: str
    time: Optional[str] = None
    label: Optional[str] = None

class AssessmentComponent(BaseModel):
    id: str
    name: str
    type: AssessmentType
    weight: float
    maxScore: float
    score: Optional[float] = None
    date: Optional[str] = None
    dateEnd: Optional[str] = None
    dateAvailable: Optional[str] = None
    time: Optional[str] = None
    slots: Optional[List[AssessmentSlot]] = None
    location: Optional[str] = None
    duration: Optional[str] = None
    studyUnits: Optional[str] = None
    dropLowest: Optional[int] = None
    required: Optional[bool] = None
    minimumExamAdmission: Optional[float] = None
    category: Optional[str] = None
    completed: Optional[bool] = None
    countsTowardCompletion: Optional[bool] = None

class FormulaComponent(BaseModel):
    componentId: str
    weight: float
    dropLowest: Optional[int] = None
    minimumCompleted: Optional[int] = None
    totalInCategory: Optional[int] = None
    useAll: Optional[bool] = None

class ParticipationFormula(BaseModel):
    components: List[FormulaComponent]
    minimumToPass: float

class PassRequirements(BaseModel):
    participationMin: Optional[float] = None
    examMin: Optional[float] = None
    finalMin: Optional[float] = None
    minimumCompletionPercent: Optional[float] = None

class ExamOpportunity(BaseModel):
    label: str
    start: str
    end: str

class ExamPaper(BaseModel):
    name: str
    maxScore: float
    duration: str
    studyUnits: str

class ExamInfo(BaseModel):
    papers: List[ExamPaper]
    finalMarkIsAverage: Optional[bool] = None
    secondOpportunityOverridesFirst: Optional[bool] = None

class ModuleGroup(BaseModel):
    id: str
    label: str
    language: str
    lecturer: str
    email: str
    office: str
    venue: Optional[str] = None
    periods: Optional[str] = None

class RecessPeriod(BaseModel):
    start: str
    end: str
    label: Optional[str] = None

class Module(BaseModel):
    moduleId: str
    code: str
    name: str
    lecturer: Optional[str] = None
    email: Optional[str] = None
    office: Optional[str] = None
    consultationHours: Optional[str] = None
    groups: Optional[List[ModuleGroup]] = None
    assessments: List[AssessmentComponent] = Field(default_factory=list)
    participationFormula: ParticipationFormula
    passRequirements: Optional[PassRequirements] = None
    semesterStart: str
    semesterEnd: str
    hasExam: bool
    examDate: Optional[str] = None
    examDateEnd: Optional[str] = None
    examOpportunities: Optional[List[ExamOpportunity]] = None
    examInfo: Optional[ExamInfo] = None
    recessPeriods: Optional[List[RecessPeriod]] = None
    color: Optional[str] = None
    addedYear: int

class Block(TypedDict):
    content: str
    bbox: Tuple[float, float, float, float]
    top: float


# exports: Module, CategoryType, Block