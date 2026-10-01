import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Sparkles, 
  CheckCircle2, 
  AlertCircle, 
  Loader2, 
  Copy, 
  Download, 
  X, 
  ExternalLink,
  BookOpen
} from 'lucide-react';
import { ResearchCard } from '../types';

interface PipelineModalProps {
  isOpen: boolean;
  onClose: () => void;
  cards: ResearchCard[];
  searchQuery?: string;
}

interface PipelineJobStatus {
  job_id: string;
  status: 'queued' | 'started' | 'finished' | 'failed';
  progress: number;
  stage: 'crawl' | 'parse' | 'load' | 'outline' | 'synthesize' | 'done' | null;
  article_id?: string | null;
  trace_id?: string | null;
  error?: string | null;
}

interface ArticleData {
  article_id: string;
  title: string;
  markdown: string;
  model: string;
  created_at: string;
}

const STAGES = [
  { id: 'crawl', name: 'Stage 1: Crawl & Playwright Extraction', desc: 'Fetching DOM, handling rate limits & soft failure rejection' },
  { id: 'parse', name: 'Stage 2: AST Ingest & Math Blocks', desc: 'Extracting typed markdown blocks, footnotes & math syntax' },
  { id: 'load', name: 'Stage 3: Neon DB Atomization', desc: 'Loading into Postgres, sentence-splitting atoms & sections' },
  { id: 'outline', name: 'Stage 4: JEV Classification', desc: 'Classifying chrome vs narrative roles across 9 buckets' },
  { id: 'synthesize', name: 'Stage 5: GLM-5.3-Flash Synthesis', desc: 'Curating, deduplicating, and composing structured article' },
];

export function PipelineModal({ isOpen, onClose, cards, searchQuery }: PipelineModalProps) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<PipelineJobStatus | null>(null);
  const [article, setArticle] = useState<ArticleData | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const pollIntervalRef = useRef<number | null>(null);
  const pollFailureCountRef = useRef(0);

  // Stop polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  const handleStartSynthesis = async () => {
    const urls = cards
      .map((c) => c.rawUrl || (c.domain ? `https://${c.domain}` : ''))
      .filter((u) => u.startsWith('http://') || u.startsWith('https://'));

    if (urls.length === 0) {
      setErrorMessage('No valid URLs found in the selected cards to crawl.');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setArticle(null);
    setJobStatus(null);

    try {
      const res = await fetch('/api/pipeline/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          urls,
          search_query: searchQuery || 'Synthesized Research Topic',
          user_id: 'research-deck-user',
          surface: 'web-deck',
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || `HTTP ${res.status}`);
      }

      setJobId(data.job_id);
      startPolling(data.job_id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const startPolling = (id: string) => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    pollFailureCountRef.current = 0;

    const recordPollingFailure = (message: string) => {
      pollFailureCountRef.current += 1;
      if (pollFailureCountRef.current >= 5) {
        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
        setErrorMessage(`Polling failed 5 consecutive times: ${message}`);
      }
    };

    pollIntervalRef.current = window.setInterval(async () => {
      try {
        const res = await fetch(`/api/pipeline/jobs/${id}`);
        if (!res.ok) {
          recordPollingFailure(`HTTP ${res.status}`);
          return;
        }

        pollFailureCountRef.current = 0;
        const data: PipelineJobStatus = await res.json();
        setJobStatus(data);

        if (data.status === 'finished') {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          if (data.article_id) {
            fetchArticle(data.article_id);
          } else {
            setErrorMessage('Job finished but no article_id returned');
          }
        } else if (data.status === 'failed') {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          setErrorMessage(data.error || 'Pipeline job failed in worker.');
        }
      } catch (err) {
        console.error('Polling error:', err);
        recordPollingFailure(err instanceof Error ? err.message : String(err));
      }
    }, 2000);
  };

  const fetchArticle = async (articleId: string) => {
    try {
      const res = await fetch(`/api/pipeline/articles/${articleId}`);
      if (res.ok) {
        const data = await res.json();
        setArticle(data);
      }
    } catch (err) {
      console.error('Failed to load article:', err);
    }
  };

  const handleCopyMarkdown = () => {
    if (!article) return;
    navigator.clipboard.writeText(article.markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!article) return;
    const blob = new Blob([article.markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(article.title || 'synthesized-article').replace(/[^a-z0-9]/gi, '_').toLowerCase()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 16 }}
          className="w-full max-w-3xl bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] text-slate-800"
          role="dialog"
          aria-label="Synthesize Research Article"
        >
          {/* Header */}
          <div className="px-6 py-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-200">
                <Sparkles className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-base font-bold text-slate-900">Backend Synthesis Pipeline</h2>
                <p className="text-xs text-slate-500">
                  5-stage pipeline across Playwright, AST parser, Neon DB, JEV & Together AI
                </p>
              </div>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Modal Content */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* If article is ready, show reader */}
            {article ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between bg-emerald-50 border border-emerald-200 p-4 rounded-xl">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                    <div>
                      <h3 className="text-sm font-bold text-emerald-950">Synthesis Complete!</h3>
                      <p className="text-xs text-emerald-700">Model: {article.model} • Synthesized via Neon Postgres corpus</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleCopyMarkdown}
                      className="px-3 py-1.5 rounded-lg bg-white border border-emerald-300 hover:bg-emerald-50 text-xs font-semibold text-emerald-800 flex items-center gap-1.5 shadow-xs"
                    >
                      <Copy className="w-3.5 h-3.5" />
                      <span>{copied ? 'Copied!' : 'Copy MD'}</span>
                    </button>
                    <button
                      onClick={handleDownload}
                      className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-xs font-semibold text-white flex items-center gap-1.5 shadow-xs"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Download .md</span>
                    </button>
                  </div>
                </div>

                <div className="p-6 bg-slate-50 rounded-xl border border-slate-200 font-serif leading-relaxed text-slate-800 max-h-[50vh] overflow-y-auto space-y-4 text-sm">
                  <h1 className="text-2xl font-bold font-sans text-slate-900">{article.title}</h1>
                  <div className="whitespace-pre-wrap font-sans text-xs text-slate-700 space-y-2">
                    {article.markdown}
                  </div>
                </div>
              </div>
            ) : jobId ? (
              /* Ongoing Job Status Display */
              <div className="space-y-5">
                <div className="bg-indigo-50/60 border border-indigo-100 rounded-xl p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Loader2 className="w-5 h-5 text-indigo-600 animate-spin" />
                    <div>
                      <span className="text-xs font-mono font-semibold text-indigo-700 uppercase">Job #{jobId}</span>
                      <h4 className="text-sm font-bold text-slate-900 capitalize">
                        {jobStatus?.stage ? `Stage: ${jobStatus.stage}` : 'Initializing pipeline...'}
                      </h4>
                    </div>
                  </div>
                  <span className="text-base font-bold font-mono text-indigo-600">
                    {jobStatus?.progress ?? 5}%
                  </span>
                </div>

                {/* Stage Progress Tracker */}
                <div className="space-y-2.5">
                  {STAGES.map((st, idx) => {
                    const stageOrder = ['crawl', 'parse', 'load', 'outline', 'synthesize', 'done'];
                    const currentStageIdx = jobStatus?.stage ? stageOrder.indexOf(jobStatus.stage) : 0;
                    const isDone = currentStageIdx > idx || jobStatus?.status === 'finished';
                    const isCurrent = jobStatus?.stage === st.id;

                    return (
                      <div
                        key={st.id}
                        className={`p-3.5 rounded-xl border transition-all flex items-start gap-3 ${
                          isCurrent
                            ? 'bg-indigo-50/50 border-indigo-200 ring-2 ring-indigo-500/10'
                            : isDone
                            ? 'bg-emerald-50/40 border-emerald-200'
                            : 'bg-slate-50/50 border-slate-200 opacity-60'
                        }`}
                      >
                        <div className="mt-0.5">
                          {isDone ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                          ) : isCurrent ? (
                            <Loader2 className="w-4 h-4 text-indigo-600 animate-spin" />
                          ) : (
                            <div className="w-4 h-4 rounded-full border border-slate-300 flex items-center justify-center text-[10px] text-slate-400">
                              {idx + 1}
                            </div>
                          )}
                        </div>
                        <div>
                          <h5 className={`text-xs font-bold ${isCurrent ? 'text-indigo-900' : isDone ? 'text-emerald-950' : 'text-slate-700'}`}>
                            {st.name}
                          </h5>
                          <p className="text-[11px] text-slate-500">{st.desc}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              /* Pre-launch confirmation */
              <div className="space-y-4">
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                  <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Selected Source Documents ({cards.length})
                  </h4>
                  <div className="max-h-40 overflow-y-auto space-y-1.5 pr-2">
                    {cards.map((c, i) => (
                      <div key={c.id} className="flex items-center justify-between text-xs py-1 px-2 rounded bg-white border border-slate-200">
                        <span className="truncate max-w-[80%] font-medium text-slate-800">
                          {i + 1}. {c.title}
                        </span>
                        <span className="text-[11px] font-mono text-slate-400">{c.domain}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-900 space-y-1">
                  <span className="font-bold flex items-center gap-1.5">
                    <BookOpen className="w-3.5 h-3.5 text-amber-700" />
                    How It Works
                  </span>
                  <p className="text-amber-800">
                    The backend crawler fetches the live pages, extracts typed blocks into Neon Postgres, classifies narrative roles with TypeSafe / JEV, and synthesizes a single unified article with Together AI GLM-5.3-Flash adhering to strict 19-rule source boundary validation.
                  </p>
                </div>
              </div>
            )}

            {/* Error Message */}
            {errorMessage && (
              <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 flex items-start gap-2.5 text-rose-800 text-xs">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                <div>
                  <h5 className="font-bold text-rose-950">Synthesis Error</h5>
                  <p>{errorMessage}</p>
                </div>
              </div>
            )}
          </div>

          {/* Footer Controls */}
          <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
            <span className="text-xs text-slate-400">
              Queue: Redis Upstash • DB: Neon Postgres
            </span>

            <div className="flex items-center gap-2">
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 text-xs font-semibold text-slate-700 transition-colors"
              >
                {article ? 'Close' : 'Cancel'}
              </button>

              {!article && !jobId && (
                <button
                  onClick={handleStartSynthesis}
                  disabled={isSubmitting || cards.length === 0}
                  className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-xs font-semibold text-white flex items-center gap-2 shadow-xs transition-colors"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Enqueueing...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Run Pipeline ({cards.length} URLs)</span>
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
