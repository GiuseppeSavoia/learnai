"""Programmi d'esame per lo studio (CFA Livelli I-III e GMAT Focus Edition).

I pesi sono APPROSSIMATIVI, ricostruiti dalle linee guida pubbliche dei curricula recenti: servono solo a
distribuire le domande fra gli argomenti, non sono le percentuali ufficiali. Controlla sempre il sito
dell'ente d'esame per il tuo anno.

Formati supportati (v1): solo domande a risposta multipla con una sola risposta giusta.
- CFA L1: domande singole, 3 opzioni.
- CFA L2/L3: domande con "vignette" (caso) incorporata in ogni domanda, 3 opzioni. Le risposte aperte
  (constructed response) del Livello III non sono supportate.
- GMAT: 5 opzioni. In Data Insights solo Data Sufficiency (opzioni canoniche fisse) e domande a risposta
  singola su tabelle/grafici; Two-Part Analysis e Multi-Source Reasoning a risposte multiple esclusi.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Topic:
    id: str
    label: str
    weight: float
    #: indicazioni per il generatore (sottoargomenti, tipi di domanda)
    focus: str = ""
    #: formato speciale: "ds" = Data Sufficiency (opzioni canoniche)
    kind: str = "mcq"


@dataclass(frozen=True)
class Exam:
    id: str
    label: str
    short: str
    description: str
    n_choices: int
    vignette: bool
    #: rating iniziale e obiettivo (scala Glicko: 1500 = livello medio da superamento)
    target_rating: int
    topics: tuple[Topic, ...] = field(default_factory=tuple)

    def topic(self, topic_id: str) -> Topic | None:
        return next((t for t in self.topics if t.id == topic_id), None)


DS_CHOICES: tuple[str, ...] = (
    "Statement (1) ALONE is sufficient, but statement (2) alone is not sufficient.",
    "Statement (2) ALONE is sufficient, but statement (1) alone is not sufficient.",
    "BOTH statements TOGETHER are sufficient, but NEITHER statement ALONE is sufficient.",
    "EACH statement ALONE is sufficient.",
    "Statements (1) and (2) TOGETHER are NOT sufficient.",
)

_CFA12_TOPICS = (
    ("ethics", "Ethical & Professional Standards", "Code and Standards, GIPS, applicazione a casi"),
    ("quant", "Quantitative Methods", "TVM, statistica, probabilità, test d'ipotesi, regressione"),
    ("econ", "Economics", "micro, macro, politica monetaria/fiscale, cambi"),
    ("fsa", "Financial Statement Analysis", "conto economico, stato patrimoniale, flussi, rimanenze, imposte, ratio"),
    ("corp", "Corporate Issuers", "governance, capital budgeting, costo del capitale, struttura del capitale"),
    ("equity", "Equity Investments", "mercati, indici, efficienza, analisi di settore, modelli di valutazione"),
    ("fixed", "Fixed Income", "pricing, yield, duration, convessità, rischio di credito, cartolarizzazioni"),
    ("deriv", "Derivatives", "forward, futures, swap, opzioni, put-call parity, modello binomiale"),
    ("alt", "Alternative Investments", "private equity/debt, real estate, hedge fund, commodity, infrastrutture"),
    ("pm", "Portfolio Management", "rischio/rendimento, CAPM, IPS, behavioral finance, risk management"),
)
_CFA1_W = {"ethics": 17.5, "quant": 7.5, "econ": 7.5, "fsa": 12.5, "corp": 7.5, "equity": 12.5,
           "fixed": 12.5, "deriv": 6.5, "alt": 8.5, "pm": 10}
_CFA2_W = {"ethics": 12.5, "quant": 7.5, "econ": 7.5, "fsa": 12.5, "corp": 7.5, "equity": 12.5,
           "fixed": 12.5, "deriv": 7.5, "alt": 7.5, "pm": 12.5}

EXAMS: dict[str, Exam] = {
    "cfa1": Exam(
        id="cfa1",
        label="CFA Livello I",
        short="CFA I",
        description="Concetti e strumenti: domande singole a 3 opzioni.",
        n_choices=3,
        vignette=False,
        target_rating=1700,
        topics=tuple(Topic(i, label, _CFA1_W[i], focus) for i, label, focus in _CFA12_TOPICS),
    ),
    "cfa2": Exam(
        id="cfa2",
        label="CFA Livello II",
        short="CFA II",
        description="Applicazione e valutazione: casi (vignette) con domande a 3 opzioni.",
        n_choices=3,
        vignette=True,
        target_rating=1700,
        topics=tuple(Topic(i, label, _CFA2_W[i], focus) for i, label, focus in _CFA12_TOPICS),
    ),
    "cfa3": Exam(
        id="cfa3",
        label="CFA Livello III",
        short="CFA III",
        description="Gestione di portafoglio: casi a 3 opzioni (le risposte aperte non sono incluse).",
        n_choices=3,
        vignette=True,
        target_rating=1700,
        topics=(
            Topic("alloc", "Asset Allocation", 17.5, "capital market expectations, asset allocation strategica e tattica, ALM"),
            Topic("constr", "Portfolio Construction", 17.5, "gestione azionaria e obbligazionaria attiva/passiva, overlay"),
            Topic("perf", "Performance Measurement", 7.5, "attribution, appraisal, benchmark, GIPS"),
            Topic("risk", "Derivatives & Risk Management", 12.5, "hedging con derivati, gestione del rischio valutario, swap"),
            Topic("ethics", "Ethical & Professional Standards", 12.5, "Code and Standards applicati a casi di gestione"),
            Topic("pathway", "Pathway: Portfolio Management", 32.5, "gestione per istituzionali, trading, esecuzione, ESG"),
        ),
    ),
    "gmat": Exam(
        id="gmat",
        label="GMAT Focus",
        short="GMAT",
        description="Quant, Verbal e Data Insights: domande a 5 opzioni.",
        n_choices=5,
        vignette=False,
        target_rating=1700,
        topics=(
            Topic("ps", "Quant — Problem Solving", 33, "aritmetica e algebra (niente geometria): percentuali, rapporti, numeri interi, equazioni, word problem"),
            Topic("cr", "Verbal — Critical Reasoning", 17, "rafforzare/indebolire, assunzioni, inferenza, valutare l'argomento, boldface"),
            Topic("rc", "Verbal — Reading Comprehension", 16, "brano di 200-350 parole incluso nel testo della domanda, idea principale, inferenza, dettaglio"),
            Topic("ds", "Data Insights — Data Sufficiency", 20, "domanda + due affermazioni (1) e (2)", kind="ds"),
            Topic("gi", "Data Insights — Tabelle e grafici", 14, "tabella o grafico descritto in testo nella domanda, una sola risposta giusta"),
        ),
    ),
}


def get_exam(exam_id: str) -> Exam | None:
    return EXAMS.get(exam_id)
