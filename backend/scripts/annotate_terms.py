"""Aggiunge il termine inglese tra parentesi ai termini tecnici italiani nei contenuti di studio.

Uso:  .venv/bin/python scripts/annotate_terms.py   (dalla cartella backend)

Modifica in place ``app/resources/study/*.json``. Annota la PRIMA occorrenza di ogni termine:
- nella lezione di ogni modulo (riassunto, paragrafi, errori tipici), una volta per modulo;
- in ogni spiegazione di domanda, una volta per spiegazione.
È idempotente: salta i termini già seguiti da "(" o il cui equivalente inglese compare già nel paragrafo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent.parent / "app" / "resources" / "study"

# (forme italiane, termine inglese). Le forme più lunghe vengono cercate per prime.
GLOSSARY: list[tuple[tuple[str, ...], str]] = [
    # metodi quantitativi
    (("valore attuale", "valori attuali"), "present value"),
    (("valore futuro",), "future value"),
    (("valore del denaro nel tempo",), "time value of money"),
    (("tasso di sconto", "tassi di sconto"), "discount rate"),
    (("tasso effettivo",), "effective rate"),
    (("capitalizzazione continua",), "continuous compounding"),
    (("perpetuità",), "perpetuity"),
    (("media aritmetica",), "arithmetic mean"),
    (("media geometrica",), "geometric mean"),
    (("media armonica",), "harmonic mean"),
    (("media ponderata",), "weighted average"),
    (("deviazione standard", "deviazioni standard"), "standard deviation"),
    (("varianza",), "variance"),
    (("covarianza",), "covariance"),
    (("correlazione",), "correlation"),
    (("coefficiente di variazione",), "coefficient of variation"),
    (("asimmetria",), "skewness"),
    (("curtosi",), "kurtosis"),
    (("probabilità condizionata",), "conditional probability"),
    (("teorema di Bayes",), "Bayes' theorem"),
    (("distribuzione normale",), "normal distribution"),
    (("teorema del limite centrale",), "central limit theorem"),
    (("errore standard", "errori standard"), "standard error"),
    (("intervallo di confidenza",), "confidence interval"),
    (("ipotesi nulla",), "null hypothesis"),
    (("test d'ipotesi",), "hypothesis testing"),
    (("livello di significatività",), "significance level"),
    (("potenza",), "power"),
    (("gradi di libertà",), "degrees of freedom"),
    (("regressione lineare",), "linear regression"),
    (("regressione multipla",), "multiple regression"),
    (("pendenza",), "slope"),
    (("intercetta",), "intercept"),
    (("residui",), "residuals"),
    (("eteroschedasticità",), "heteroskedasticity"),
    (("omoschedasticità",), "homoskedasticity"),
    (("correlazione seriale",), "serial correlation"),
    (("multicollinearità",), "multicollinearity"),
    (("serie storiche", "serie storica"), "time series"),
    (("radice unitaria",), "unit root"),
    (("ritorno alla media",), "mean reversion"),
    (("apprendimento supervisionato",), "supervised learning"),
    (("apprendimento non supervisionato",), "unsupervised learning"),
    (("sovradattamento",), "overfitting"),
    (("campionamento",), "sampling"),
    # economia
    (("elasticità della domanda",), "elasticity of demand"),
    (("ricavo marginale",), "marginal revenue"),
    (("costo marginale",), "marginal cost"),
    (("ricavo totale",), "total revenue"),
    (("concorrenza perfetta",), "perfect competition"),
    (("concorrenza monopolistica",), "monopolistic competition"),
    (("oligopolio",), "oligopoly"),
    (("ciclo economico",), "business cycle"),
    (("indicatori anticipatori",), "leading indicators"),
    (("politica monetaria",), "monetary policy"),
    (("politica fiscale",), "fiscal policy"),
    (("stabilizzatori automatici",), "automatic stabilizers"),
    (("banca centrale",), "central bank"),
    (("tasso di cambio", "tassi di cambio"), "exchange rate"),
    (("cambio a pronti",), "spot rate"),
    (("parità coperta dei tassi d'interesse", "parità coperta"), "covered interest rate parity"),
    (("parità scoperta",), "uncovered interest rate parity"),
    (("parità dei poteri d'acquisto", "PPP relativa"), "purchasing power parity"),
    (("bilancia dei pagamenti",), "balance of payments"),
    (("parte corrente",), "current account"),
    (("produttività totale dei fattori",), "total factor productivity"),
    (("disoccupazione",), "unemployment"),
    (("inflazione",), "inflation"),
    # analisi di bilancio
    (("conto economico",), "income statement"),
    (("stato patrimoniale",), "balance sheet"),
    (("rendiconto finanziario",), "cash flow statement"),
    (("patrimonio netto",), "equity"),
    (("utile netto",), "net income"),
    (("utile per azione",), "earnings per share"),
    (("costo del venduto",), "cost of goods sold"),
    (("rimanenze",), "inventories"),
    (("ammortamento", "ammortamenti"), "depreciation"),
    (("capitalizzare",), "capitalize"),
    (("imposte differite",), "deferred taxes"),
    (("differenze temporanee",), "temporary differences"),
    (("perdite riportabili",), "tax loss carryforwards"),
    (("capitale circolante",), "working capital"),
    (("ciclo di cassa",), "cash conversion cycle"),
    (("indice di liquidità corrente",), "current ratio"),
    (("rotazione delle attività",), "asset turnover"),
    (("margine netto",), "net profit margin"),
    (("leva finanziaria",), "financial leverage"),
    (("leva operativa",), "operating leverage"),
    (("svalutazione",), "impairment"),
    (("qualità degli utili",), "earnings quality"),
    (("metodo del patrimonio netto",), "equity method"),
    (("consolidamento integrale", "consolidamento"), "consolidation"),
    (("interessenze di minoranza",), "non-controlling interests"),
    (("avviamento",), "goodwill"),
    (("influenza significativa",), "significant influence"),
    (("piani pensionistici a benefici definiti", "fondo pensione", "fondi pensione"), "defined benefit pension plan"),
    (("obbligazione pensionistica",), "pension obligation"),
    (("metodo del cambio corrente",), "current rate method"),
    (("metodo temporale",), "temporal method"),
    (("valuta funzionale",), "functional currency"),
    # emittenti
    (("costo del capitale",), "cost of capital"),
    (("costo dell'equity",), "cost of equity"),
    (("costo del debito",), "cost of debt"),
    (("struttura del capitale",), "capital structure"),
    (("scudo fiscale",), "tax shield"),
    (("costi di dissesto",), "costs of financial distress"),
    (("costi irrecuperabili", "costo sunk"), "sunk costs"),
    (("costo opportunità", "costi opportunità"), "opportunity cost"),
    (("cannibalizzazione",), "cannibalization"),
    (("valore attuale netto",), "net present value"),
    (("tasso interno di rendimento",), "internal rate of return"),
    (("periodo di recupero",), "payback period"),
    (("riacquisto di azioni", "riacquisti di azioni", "riacquisti", "riacquisto"), "share repurchase"),
    (("dividendi", "dividendo"), "dividends"),
    (("tasso di ritenzione",), "retention rate"),
    (("premio per il rischio paese",), "country risk premium"),
    (("consiglio di amministrazione",), "board of directors"),
    # azionario
    (("margine iniziale",), "initial margin"),
    (("margine di mantenimento",), "maintenance margin"),
    (("vendita allo scoperto",), "short sale"),
    (("forma debole",), "weak form"),
    (("forma semi-forte",), "semi-strong form"),
    (("forma forte",), "strong form"),
    (("efficienza dei mercati",), "market efficiency"),
    (("cinque forze",), "five forces"),
    (("rendimento richiesto",), "required return"),
    (("tasso di crescita sostenibile",), "sustainable growth rate"),
    (("valore terminale",), "terminal value"),
    (("valore intrinseco",), "intrinsic value"),
    (("azioni privilegiate",), "preferred stock"),
    (("multipli",), "multiples"),
    (("flussi di cassa liberi",), "free cash flows"),
    (("utile residuo",), "residual income"),
    (("valore d'impresa",), "enterprise value"),
    # reddito fisso
    (("obbligazioni", "obbligazione"), "bonds"),
    (("cedola", "cedole"), "coupon"),
    (("rendimento a scadenza",), "yield to maturity"),
    (("rateo d'interesse", "rateo"), "accrued interest"),
    (("prezzo secco",), "flat price"),
    (("prezzo tel quel",), "full price"),
    (("curva dei tassi", "curva dei rendimenti"), "yield curve"),
    (("tassi spot", "tasso spot"), "spot rates"),
    (("tassi forward", "tasso forward"), "forward rates"),
    (("struttura a termine",), "term structure"),
    (("convessità",), "convexity"),
    (("rischio di reinvestimento",), "reinvestment risk"),
    (("immunizzazione",), "immunization"),
    (("rischio di credito",), "credit risk"),
    (("probabilità di default",), "probability of default"),
    (("tasso di recupero",), "recovery rate"),
    (("perdita attesa",), "expected loss"),
    (("cartolarizzazioni", "cartolarizzazione"), "securitization"),
    (("rimborso anticipato",), "prepayment"),
    (("titolo di Stato", "titoli di Stato"), "government bond"),
    (("valutazione senza arbitraggio", "non arbitraggio", "assenza di arbitraggio"), "no-arbitrage"),
    # derivati
    (("derivati",), "derivatives"),
    (("contratti a termine", "contratto a termine"), "forward contracts"),
    (("stanza di compensazione",), "clearinghouse"),
    (("rischio di controparte",), "counterparty risk"),
    (("opzioni", "opzione"), "options"),
    (("prezzo di esercizio",), "strike price"),
    (("premio per il rischio di mercato",), "market risk premium"),
    (("premio per il rischio",), "risk premium"),
    (("premio di controllo",), "control premium"),
    (("valore temporale",), "time value"),
    (("probabilità neutrale al rischio", "probabilità neutrali al rischio"), "risk-neutral probability"),
    (("albero binomiale",), "binomial tree"),
    (("copertura", "coperture"), "hedging"),
    (("costi di detenzione",), "carrying costs"),
    # alternativi
    (("investimenti alternativi",), "alternative investments"),
    (("commissione di gestione",), "management fee"),
    (("commissione di performance",), "incentive fee"),
    (("soglia minima",), "hurdle rate"),
    (("immobiliare",), "real estate"),
    (("reddito operativo netto",), "net operating income"),
    (("tasso di capitalizzazione",), "capitalization rate"),
    (("materie prime",), "commodities"),
    (("illiquidità",), "illiquidity"),
    # portafoglio
    (("frontiera efficiente",), "efficient frontier"),
    (("portafoglio di mercato",), "market portfolio"),
    (("rischio sistematico",), "systematic risk"),
    (("rischio specifico",), "idiosyncratic risk"),
    (("diversificazione",), "diversification"),
    (("tolleranza al rischio",), "risk tolerance"),
    (("propensione al rischio",), "willingness to take risk"),
    (("capacità di sopportare il rischio", "capacità di rischio"), "ability to take risk"),
    (("orizzonte temporale",), "time horizon"),
    (("finanza comportamentale",), "behavioral finance"),
    (("avversione alle perdite",), "loss aversion"),
    (("eccesso di fiducia",), "overconfidence"),
    (("rendimento attivo",), "active return"),
    (("rischio attivo",), "active risk"),
    (("errore di replica",), "tracking error"),
    (("legge fondamentale",), "fundamental law of active management"),
    (("coefficiente di trasferimento",), "transfer coefficient"),
    (("ribilanciamento",), "rebalancing"),
    (("aspettative di mercato",), "capital market expectations"),
    (("passività",), "liabilities"),
    (("attribuzione della performance", "attribuzione"), "performance attribution"),
    (("effetto allocazione",), "allocation effect"),
    (("effetto selezione",), "selection effect"),
    (("regola di spesa",), "spending rule"),
    (("costo di esecuzione", "costi di esecuzione"), "execution cost"),
    (("costo opportunità della parte non eseguita",), "opportunity cost"),
    # etica
    (("informazioni privilegiate",), "material nonpublic information"),
    (("riservatezza",), "confidentiality"),
    (("adeguatezza",), "suitability"),
    (("trattamento equo",), "fair dealing"),
    (("conflitti di interesse", "conflitto di interesse"), "conflicts of interest"),
    (("indipendenza e obiettività",), "independence and objectivity"),
    (("dovere di lealtà",), "duty of loyalty"),
    (("supervisore",), "supervisor"),
    # GMAT
    (("velocità media",), "average speed"),
    (("variazione percentuale",), "percent change"),
    (("resti",), "remainders"),
    (("divisibilità",), "divisibility"),
    (("numeri primi", "numero primo"), "prime numbers"),
    (("combinazioni",), "combinations"),
    (("permutazioni",), "permutations"),
    (("inclusione-esclusione",), "inclusion-exclusion"),
    (("premesse", "premessa"), "premises"),
    (("conclusione",), "conclusion"),
    (("assunzione",), "assumption"),
    (("rafforzare",), "strengthen"),
    (("indebolire",), "weaken"),
    (("inferenza",), "inference"),
    (("idea principale",), "main idea"),
    (("sufficienza",), "sufficiency"),
]

_PATTERNS: list[tuple[re.Pattern[str], str]] = []
for forms, english in GLOSSARY:
    for form in forms:
        _PATTERNS.append((re.compile(rf"(?<!\w)({re.escape(form)})(?!\w)", re.IGNORECASE), english))
_PATTERNS.sort(key=lambda p: -len(p[0].pattern))


def annotate(text: str, seen: set[str]) -> str:
    """Annota la prima occorrenza (non già vista in `seen`) di ogni termine nel testo."""
    spans: list[tuple[int, int, str]] = []
    lowered = text.lower()
    for pattern, english in _PATTERNS:
        if english in seen:
            continue
        for m in pattern.finditer(text):
            start, end = m.span(1)
            if any(start < e and end > s for s, e, _ in spans):
                continue
            if re.match(r"\s*\([^\W\d_]", text[end:]) or english.lower() in lowered:
                seen.add(english)
                break
            spans.append((start, end, english))
            seen.add(english)
            break
    for start, end, english in sorted(spans, reverse=True):
        text = f"{text[:end]} ({english}){text[end:]}"
    return text


def _annotate_question(q: dict) -> None:
    q["explanation"] = annotate(q["explanation"], set())


def process(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    before = json.dumps(data, ensure_ascii=False)
    for module in data["modules"]:
        seen: set[str] = set()
        if "summary" in module:
            module["summary"] = annotate(module["summary"], seen)
        for section in module.get("sections", []):
            section["body"] = [annotate(p, seen) for p in section["body"]]
        module["pitfalls"] = [annotate(p, seen) for p in module.get("pitfalls", [])]
        for q in module.get("questions", []):
            _annotate_question(q)
        for item_set in module.get("item_sets", []):
            for q in item_set["questions"]:
                _annotate_question(q)
    after = json.dumps(data, ensure_ascii=False)
    if after != before:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return after.count(") ") - before.count(") ")


if __name__ == "__main__":
    for p in sorted(CONTENT_DIR.glob("*.json")):
        process(p)
        print(f"annotato: {p.name}")
