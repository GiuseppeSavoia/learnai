import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  type StudyAnswerResult,
  type StudyModule,
  type StudyQuestion,
} from "../api/client";
import {
  Card,
  ErrorBox,
  Loading,
  PageHeader,
  ProgressBar,
} from "../components/ui";
import { errMsg, useAsync } from "../hooks/useAsync";

const LETTERS = "ABCDE";
const DIFFICULTY = [
  "",
  "facile",
  "medio-facile",
  "media",
  "difficile",
  "molto difficile",
];

/** Stile dei paragrafi della lezione: esempi svolti e trappole d'esame evidenziati. */
function paraClass(para: string): string | undefined {
  if (para.startsWith("Esempio")) return "lesson-example";
  if (para.startsWith("Trappola")) return "lesson-trap";
  return undefined;
}

/** Rimonta la pagina quando cambia esame, così lo stato (domanda, argomento) riparte pulito. */
export default function StudyPage() {
  const { exam = "" } = useParams();
  return <StudyExam key={exam} exam={exam} />;
}

function StudyExam({ exam }: { exam: string }) {
  const detail = useAsync(() => api.getStudyExam(exam), [exam]);
  const [tab, setTab] = useState<"path" | "practice">("path");
  const [topic, setTopic] = useState("");
  const [question, setQuestion] = useState<StudyQuestion | null>(null);
  const [loadingQ, setLoadingQ] = useState(false);
  const [qError, setQError] = useState<string | null>(null);
  const [choice, setChoice] = useState<number | null>(null);
  const [result, setResult] = useState<StudyAnswerResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [flagged, setFlagged] = useState(false);
  const started = useRef(0);

  const loadNext = async (topicOverride?: string) => {
    const t = topicOverride ?? topic;
    setLoadingQ(true);
    setQError(null);
    setResult(null);
    setChoice(null);
    setFlagged(false);
    try {
      setQuestion(await api.nextStudyQuestion(exam, t || undefined));
      started.current = Date.now();
    } catch (e) {
      setQError(errMsg(e));
    } finally {
      setLoadingQ(false);
    }
  };

  const submit = async () => {
    if (!question || choice === null) return;
    setSubmitting(true);
    try {
      setResult(
        await api.answerStudyQuestion(question.id, {
          choice,
          time_ms: Date.now() - started.current,
        }),
      );
      detail.reload();
    } catch (e) {
      setQError(errMsg(e));
    } finally {
      setSubmitting(false);
    }
  };

  const flag = async () => {
    if (!question) return;
    try {
      await api.flagStudyQuestion(question.id);
      setFlagged(true);
      detail.reload();
    } catch (e) {
      setQError(errMsg(e));
    }
  };

  const practice = (topicId: string) => {
    setTopic(topicId);
    setTab("practice");
    void loadNext(topicId);
  };

  const d = detail.data;
  const topics = d ? [...d.topics].sort((a, b) => b.weakness - a.weakness) : [];

  return (
    <div className="page">
      <PageHeader title={d?.label ?? "Studio"} subtitle={d?.description}>
        {d && (
          <span className="muted small">
            Rating <b>{d.rating}</b> · {d.answered} risposte
            {d.accuracy !== null && ` · ${Math.round(d.accuracy * 100)}%`}
          </span>
        )}
      </PageHeader>
      {detail.error && (
        <ErrorBox error={detail.error} onRetry={detail.reload} />
      )}

      <div className="segmented study-tabs">
        <button
          className={tab === "path" ? "active" : ""}
          onClick={() => setTab("path")}
        >
          Percorso
        </button>
        <button
          className={tab === "practice" ? "active" : ""}
          onClick={() => setTab("practice")}
        >
          Esercitati
        </button>
      </div>

      <div className="study-layout">
        <div className="study-main">
          {tab === "path" && <PathView exam={exam} onPractice={practice} />}
          {tab === "practice" && (
            <>
              <Card>
                <div className="study-controls">
                  <label className="study-topic">
                    <span className="field-label">Argomento</span>
                    <select
                      value={topic}
                      onChange={(ev) => setTopic(ev.target.value)}
                    >
                      <option value="">
                        Automatico (pesato sulle tue debolezze)
                      </option>
                      {d?.topics.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="btn primary"
                    onClick={() => loadNext()}
                    disabled={loadingQ || !d}
                  >
                    {question ? "Prossima domanda" : "Inizia"}
                  </button>
                </div>
                {d && !d.claude_enabled && d.bank_unseen === 0 && (
                  <p className="muted small">
                    Hai completato le domande integrate: per generarne altre con
                    Claude (a pagamento) aggiungi una chiave API in{" "}
                    <Link className="link" to="/impostazioni">
                      Impostazioni
                    </Link>
                    .
                  </p>
                )}
              </Card>

              {loadingQ && (
                <Card>
                  <Loading text="Preparo la domanda… (se le domande integrate sono finite, Claude ne genera di nuove: può richiedere fino a un minuto)" />
                </Card>
              )}
              {qError && <ErrorBox error={qError} onRetry={() => loadNext()} />}

              {question && !loadingQ && (
                <Card
                  title={
                    <>
                      {question.topic_label}{" "}
                      <span className="chip">
                        {DIFFICULTY[question.difficulty]}
                      </span>
                    </>
                  }
                >
                  {question.vignette && (
                    <div className="vignette">{question.vignette}</div>
                  )}
                  <p className="question-stem">{question.stem}</p>
                  <div className="choices">
                    {question.choices.map((c, i) => {
                      let cls = "choice";
                      if (result) {
                        if (i === result.answer) cls += " right";
                        else if (i === choice) cls += " wrong";
                      } else if (i === choice) cls += " selected";
                      return (
                        <button
                          key={i}
                          className={cls}
                          disabled={!!result}
                          onClick={() => setChoice(i)}
                        >
                          <span className="choice-letter">{LETTERS[i]}</span>
                          <span>{c}</span>
                        </button>
                      );
                    })}
                  </div>

                  {!result ? (
                    <button
                      className="btn primary"
                      disabled={choice === null || submitting}
                      onClick={submit}
                    >
                      {submitting ? "Verifica…" : "Conferma risposta"}
                    </button>
                  ) : (
                    <>
                      <div
                        className={`result-banner ${result.correct ? "win" : "loss"}`}
                      >
                        <span>
                          {result.correct
                            ? "✓ Corretto"
                            : `✗ Sbagliato: la risposta giusta è ${LETTERS[result.answer]}`}
                        </span>
                        {result.rated && (
                          <span className="delta">
                            {result.rating_delta >= 0 ? "+" : ""}
                            {result.rating_delta.toFixed(1)} →{" "}
                            {result.rating_after}
                          </span>
                        )}
                      </div>
                      <p className="explanation">{result.explanation}</p>
                      <div className="btn-row">
                        <button
                          className="btn primary"
                          onClick={() => loadNext()}
                        >
                          Prossima domanda
                        </button>
                        <button
                          className="btn ghost small"
                          onClick={flag}
                          disabled={flagged}
                          title="Esclude la domanda e annulla il suo effetto sul rating"
                        >
                          {flagged ? "Segnalata ✓" : "⚑ Segnala domanda errata"}
                        </button>
                      </div>
                    </>
                  )}
                </Card>
              )}
            </>
          )}
        </div>

        <div className="study-side">
          <Card title="Progresso">
            {detail.loading && !d && <Loading />}
            {d && (
              <>
                <ProgressBar
                  value={d.progress_pct}
                  label={`${d.rating} → ${d.target_rating}`}
                />
                <p className="muted small">
                  {d.bank_unseen} domande pronte · {d.bank_total} in banca
                </p>
              </>
            )}
          </Card>
          <Card title="Argomenti">
            <ul className="weak-list">
              {topics.map((t) => (
                <li key={t.id}>
                  <div className="weak-head">
                    <span>{t.label}</span>
                    <span className="muted small">
                      {t.accuracy === null
                        ? "mai provato"
                        : `${Math.round(t.accuracy * 100)}% su ${t.attempts}`}{" "}
                      · peso ~{t.weight_pct}%
                    </span>
                  </div>
                  <div className="weak-bar">
                    <div
                      className="weak-fill"
                      style={{
                        width: `${t.accuracy === null ? 0 : Math.round(t.accuracy * 100)}%`,
                        background:
                          t.accuracy !== null && t.accuracy < 0.6
                            ? "var(--danger)"
                            : "var(--ok)",
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
            <p className="muted small">
              I pesi sono approssimativi, non le percentuali ufficiali
              dell'esame.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}

function PathView({
  exam,
  onPractice,
}: {
  exam: string;
  onPractice: (topic: string) => void;
}) {
  const path = useAsync(() => api.getStudyPath(exam), [exam]);
  const [open, setOpen] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const toggleDone = async (m: StudyModule) => {
    setErr(null);
    try {
      path.setData(await api.setLessonDone(exam, m.topic, !m.lesson_done));
    } catch (e) {
      setErr(errMsg(e));
    }
  };

  if (path.error) return <ErrorBox error={path.error} onRetry={path.reload} />;
  if (!path.data) return <Loading />;
  const modules = path.data.modules;
  const done = modules.filter((m) => m.lesson_done).length;
  const mastered = modules.filter((m) => m.mastered).length;
  const current =
    open ?? modules.find((m) => !m.lesson_done || !m.mastered)?.topic ?? null;

  return (
    <>
      <Card>
        <p className="muted small">
          Segui i moduli in ordine: studia la lezione, segnala come studiata ed
          esercitati finché l'argomento è padroneggiato (almeno 5 risposte con
          il 70% di corrette). Lezioni studiate {done}/{modules.length} ·
          argomenti padroneggiati {mastered}/{modules.length}.
        </p>
        <ProgressBar
          value={(mastered / Math.max(1, modules.length)) * 100}
          label={`${mastered}/${modules.length} padroneggiati`}
        />
      </Card>
      {err && <ErrorBox error={err} />}
      {modules.map((m) => {
        const isOpen = current === m.topic;
        const status = m.mastered
          ? "✓ padroneggiato"
          : m.lesson_done
            ? "lezione studiata"
            : "da studiare";
        return (
          <Card
            key={m.topic}
            className={`lesson ${isOpen ? "open" : ""}`}
            title={
              <button
                className="lesson-head"
                onClick={() => setOpen(isOpen ? "" : m.topic)}
                aria-expanded={isOpen}
              >
                <span
                  className={`lesson-step ${m.mastered ? "mastered" : m.lesson_done ? "done" : ""}`}
                >
                  {m.mastered ? "✓" : m.step}
                </span>
                <span>{m.title}</span>
              </button>
            }
            actions={
              <span className="muted small">
                {status}
                {m.accuracy !== null &&
                  ` · ${Math.round(m.accuracy * 100)}% su ${m.attempts}`}
              </span>
            }
          >
            {isOpen && (
              <div className="lesson-body">
                <p className="lesson-summary">{m.summary}</p>
                {m.sections.length > 5 && (
                  <nav className="lesson-toc" aria-label="Indice della lezione">
                    <span className="muted small">Indice</span>
                    <ol>
                      {m.sections.map((sec, i) => (
                        <li key={sec.title}>
                          <a
                            href={`#${m.topic}-s${i}`}
                            onClick={(e) => {
                              e.preventDefault();
                              document
                                .getElementById(`${m.topic}-s${i}`)
                                ?.scrollIntoView({ block: "start" });
                            }}
                          >
                            {sec.title}
                          </a>
                        </li>
                      ))}
                    </ol>
                  </nav>
                )}
                {m.sections.map((sec, i) => (
                  <section key={sec.title} id={`${m.topic}-s${i}`}>
                    <h3>{sec.title}</h3>
                    {sec.body.map((para, j) => (
                      <p key={j} className={paraClass(para)}>
                        {para}
                      </p>
                    ))}
                  </section>
                ))}
                {m.formulas.length > 0 && (
                  <section>
                    <h3>Formule da sapere</h3>
                    <ul className="formula-list">
                      {m.formulas.map((f) => (
                        <li key={f}>
                          <code>{f}</code>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
                <section>
                  <h3>Errori tipici</h3>
                  <ul className="tips">
                    {m.pitfalls.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                </section>
                <div className="btn-row">
                  <button
                    className="btn primary"
                    onClick={() => onPractice(m.topic)}
                  >
                    Esercitati ({m.n_questions} domande integrate)
                  </button>
                  <button className="btn ghost" onClick={() => toggleDone(m)}>
                    {m.lesson_done
                      ? "Segna come da ripassare"
                      : "Segna come studiata"}
                  </button>
                </div>
              </div>
            )}
          </Card>
        );
      })}
    </>
  );
}
