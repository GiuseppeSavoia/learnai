// Mock in memoria delle rotte /study e /settings/claude (VITE_MOCK=1).
import { ApiError } from './client'
import type { ClaudeSettings, StudyAnswerResult, StudyExamDetail, StudyPath, StudyQuestion, StudyTopic } from './client'

interface MockExam {
  id: string
  label: string
  short: string
  description: string
  nChoices: number
  topics: [string, string, number][]
  rating: number
  answered: number
  correct: number
  stats: Record<string, { attempts: number; errors: number }>
}

const CFA_TOPICS: [string, string, number][] = [
  ['ethics', 'Ethical & Professional Standards', 17.5],
  ['quant', 'Quantitative Methods', 7.5],
  ['econ', 'Economics', 7.5],
  ['fsa', 'Financial Statement Analysis', 12.5],
  ['corp', 'Corporate Issuers', 7.5],
  ['equity', 'Equity Investments', 12.5],
  ['fixed', 'Fixed Income', 12.5],
  ['deriv', 'Derivatives', 6.5],
  ['alt', 'Alternative Investments', 8.5],
  ['pm', 'Portfolio Management', 10],
]

const exams: MockExam[] = [
  { id: 'cfa1', label: 'CFA Livello I', short: 'CFA I', description: 'Concetti e strumenti: domande singole a 3 opzioni.', nChoices: 3, topics: CFA_TOPICS, rating: 1300, answered: 0, correct: 0, stats: {} },
  { id: 'cfa2', label: 'CFA Livello II', short: 'CFA II', description: 'Applicazione e valutazione: casi (vignette) con domande a 3 opzioni.', nChoices: 3, topics: CFA_TOPICS, rating: 1300, answered: 0, correct: 0, stats: {} },
  {
    id: 'cfa3', label: 'CFA Livello III', short: 'CFA III', description: 'Gestione di portafoglio: casi a 3 opzioni (le risposte aperte non sono incluse).', nChoices: 3,
    topics: [['alloc', 'Asset Allocation', 17.5], ['constr', 'Portfolio Construction', 17.5], ['perf', 'Performance Measurement', 7.5], ['risk', 'Derivatives & Risk Management', 12.5], ['ethics', 'Ethical & Professional Standards', 12.5], ['pathway', 'Pathway: Portfolio Management', 32.5]],
    rating: 1300, answered: 0, correct: 0, stats: {},
  },
  {
    id: 'gmat', label: 'GMAT Focus', short: 'GMAT', description: 'Quant, Verbal e Data Insights: domande a 5 opzioni.', nChoices: 5,
    topics: [['ps', 'Quant — Problem Solving', 33], ['cr', 'Verbal — Critical Reasoning', 17], ['rc', 'Verbal — Reading Comprehension', 16], ['ds', 'Data Insights — Data Sufficiency', 20], ['gi', 'Data Insights — Tabelle e grafici', 14]],
    rating: 1300, answered: 0, correct: 0, stats: {},
  },
]

const lessonsDone = new Set<string>()

function path(e: MockExam): StudyPath {
  return {
    exam: e.id,
    label: e.label,
    modules: e.topics.map(([id, label], i) => {
      const st = e.stats[id] ?? { attempts: 0, errors: 0 }
      const accuracy = st.attempts ? (st.attempts - st.errors) / st.attempts : null
      return {
        step: i + 1, topic: id, topic_label: label, title: `${label} (mock)`,
        summary: 'Riassunto di esempio del modulo: nel backend vero qui c\'è la lezione completa.',
        sections: [
          { title: 'Concetti chiave', body: ['Primo paragrafo di esempio.', 'Secondo paragrafo di esempio.'] },
          { title: 'Applicazioni', body: ['Esempio di applicazione.'] },
        ],
        formulas: ['EAR = (1 + r/m)^m - 1'],
        pitfalls: ['Errore tipico di esempio.'],
        n_questions: 6, lesson_done: lessonsDone.has(`${e.id}:${id}`),
        attempts: st.attempts, accuracy, mastered: st.attempts >= 5 && (accuracy ?? 0) >= 0.7,
      }
    }),
  }
}

let claude: ClaudeSettings = { enabled: true, source: 'settings', model: 'claude-opus-5-5' }
let nextId = 1
const questions = new Map<number, StudyQuestion & { answer: number; explanation: string; answered: boolean }>()

function bad(status: number, msg: string): never {
  throw new ApiError(status, msg)
}

function exam(id: string): MockExam {
  return exams.find((e) => e.id === id) ?? bad(400, `Esame sconosciuto: ${id}`)
}

function summary(e: MockExam) {
  return {
    id: e.id, label: e.label, short: e.short, description: e.description,
    rating: Math.round(e.rating), rd: 200, target_rating: 1700,
    progress_pct: Math.max(0, Math.min(100, ((e.rating - 1300) / 400) * 100)),
    answered: e.answered, accuracy: e.answered ? e.correct / e.answered : null,
    bank_total: [...questions.values()].filter((q) => q.exam === e.id).length,
    bank_unseen: [...questions.values()].filter((q) => q.exam === e.id && !q.answered).length,
  }
}

function detail(e: MockExam): StudyExamDetail {
  const total = e.topics.reduce((s, t) => s + t[2], 0)
  const topics: StudyTopic[] = e.topics.map(([id, label, w]) => {
    const st = e.stats[id] ?? { attempts: 0, errors: 0 }
    return {
      id, label, weight_pct: Math.round((w / total) * 1000) / 10, attempts: st.attempts, errors: st.errors,
      accuracy: st.attempts ? (st.attempts - st.errors) / st.attempts : null,
      weakness: (st.errors + 1) / (st.attempts + 4),
    }
  })
  return { ...summary(e), claude_enabled: claude.enabled, topics }
}

function makeQuestion(e: MockExam, topicId?: string): StudyQuestion {
  const topic = (topicId ? e.topics.find((t) => t[0] === topicId) : e.topics[Math.floor(Math.random() * e.topics.length)]) ?? bad(400, 'Argomento sconosciuto')
  const id = nextId++
  const choices = ['5.21%', '4.87%', '5.64%', '6.02%', '4.40%'].slice(0, e.nChoices)
  const q = {
    id, exam: e.id, topic: topic[0], topic_label: topic[1], difficulty: 3,
    vignette: e.id === 'cfa2' || e.id === 'cfa3' ? 'Maria Rossi, CFA, manages a fixed-income portfolio for a pension fund. She is evaluating a 5-year annual-pay bond with a 5% coupon priced at 98.50 per 100 of par.' : '',
    stem: `(Mock) A 5-year annual-pay bond with a 5% coupon is priced at 98.50. Its yield-to-maturity is closest to:`,
    choices, answer: 0,
    explanation: 'Esempio mock: lo YTM è il tasso che eguaglia il prezzo al valore attuale dei flussi. Con prezzo sotto la pari, lo YTM supera la cedola (5%): circa 5.35%, quindi la risposta più vicina.',
    answered: false,
  }
  questions.set(id, q)
  const { answer: _a, explanation: _e, answered: _d, ...pub } = q
  return pub
}

export function studyRoute(method: string, seg: string[], q: URLSearchParams, b: Record<string, unknown>): unknown {
  const key = `${method} /${seg.join('/')}`
  if (key === 'GET /settings/claude') return claude
  if (key === 'PUT /settings/claude') {
    const k = String(b.api_key ?? '')
    claude = { ...claude, enabled: k !== '', source: k ? 'settings' : null }
    return claude
  }
  if (key === 'GET /study/exams') return { claude_enabled: claude.enabled, exams: exams.map(summary) }
  if (seg[1] === 'exams' && seg.length === 3 && method === 'GET') return detail(exam(seg[2]))
  if (seg[1] === 'exams' && seg[3] === 'path' && method === 'GET') return path(exam(seg[2]))
  if (seg[1] === 'exams' && seg[3] === 'lessons' && method === 'PUT') {
    const k = `${seg[2]}:${seg[4]}`
    if (b.done) lessonsDone.add(k)
    else lessonsDone.delete(k)
    return path(exam(seg[2]))
  }
  if (seg[1] === 'exams' && seg[3] === 'next' && method === 'GET') {
    if (!claude.enabled) bad(503, 'Serve una chiave API Anthropic per generare le domande: aggiungila in Impostazioni.')
    return makeQuestion(exam(seg[2]), q.get('topic') ?? undefined)
  }
  if (seg[1] === 'questions' && method === 'POST') {
    const question = questions.get(Number(seg[2])) ?? bad(404, 'Domanda non trovata')
    const e = exam(question.exam)
    if (seg[3] === 'flag') return { flagged: true, rating_restored: 0 }
    const choice = Number(b.choice)
    const correct = choice === question.answer
    const rated = !question.answered
    const before = e.rating
    if (rated) {
      e.rating += correct ? 18 : -14
      e.answered++
      if (correct) e.correct++
      const st = (e.stats[question.topic] ??= { attempts: 0, errors: 0 })
      st.attempts++
      if (!correct) st.errors++
    }
    question.answered = true
    const res: StudyAnswerResult = {
      correct, answer: question.answer, explanation: question.explanation, rated,
      rating_before: Math.round(before), rating_after: Math.round(e.rating), rating_delta: e.rating - before,
    }
    return res
  }
  bad(404, `Mock: endpoint non gestito ${key}`)
}
