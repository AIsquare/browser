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
  Printer,
  FileText,
  FileCode,
  Globe,
  ChevronDown
} from 'lucide-react';
import { ResearchCard } from '../types';

interface PipelineModalProps {
  key?: string;
  isOpen: boolean;
  onClose: () => void;
  cards: ResearchCard[];
  searchQuery?: string;
}

interface PipelineJobStatus {
  job_id: string;
  status: 'queued' | 'started' | 'finished' | 'failed';
  progress: number;
  stage: string | null;
  article_id?: string | null;
  error?: string | null;
}

interface ArticleData {
  article_id: string;
  title: string;
  markdown: string;
  model: string;
  created_at: string;
}

export function PipelineModal({ isOpen, onClose, cards, searchQuery }: PipelineModalProps) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<PipelineJobStatus | null>(null);
  const [article, setArticle] = useState<ArticleData | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [viewMode, setViewMode] = useState<'formatted' | 'source'>('formatted');
  const [fontSize, setFontSize] = useState<'sm' | 'base' | 'lg'>('base');
  const [showDownloadMenu, setShowDownloadMenu] = useState(false);

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
      setErrorMessage('No valid URLs found in the selected cards.');
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
          search_query: searchQuery || 'Research Synthesis Dossier',
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
      if (pollFailureCountRef.current >= 6) {
        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
        setErrorMessage(`Polling failed: ${message}`);
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
            setErrorMessage('Synthesis completed but no article ID was returned.');
          }
        } else if (data.status === 'failed') {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          setErrorMessage(data.error || 'Synthesis process failed.');
        }
      } catch (err) {
        recordPollingFailure(err instanceof Error ? err.message : String(err));
      }
    }, 1500);
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

  const downloadFile = (content: string, filename: string, type: string) => {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setShowDownloadMenu(false);
  };

  const getSlug = () => {
    return (article?.title || 'research-synthesis').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  };

  const handleDownloadMarkdown = () => {
    if (!article) return;
    downloadFile(article.markdown, `${getSlug()}.md`, 'text/markdown;charset=utf-8');
  };

  const handleDownloadText = () => {
    if (!article) return;
    const plainText = article.markdown
      .replace(/^#+\s+/gm, '')
      .replace(/^\s*>\s+/gm, '')
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
    downloadFile(plainText, `${getSlug()}.txt`, 'text/plain;charset=utf-8');
  };

  const handleDownloadHtml = () => {
    if (!article) return;
    const htmlDoc = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>${article.title}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.75; max-width: 820px; margin: 40px auto; padding: 0 24px; color: #1e293b; background: #ffffff; }
    h1 { font-size: 2.2em; line-height: 1.25; margin-bottom: 0.3em; color: #0f172a; font-weight: 800; }
    h2 { font-size: 1.45em; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.3em; margin-top: 1.8em; color: #0f172a; }
    h3 { font-size: 1.2em; margin-top: 1.4em; color: #1e293b; }
    blockquote { border-left: 3px solid #6366f1; padding: 12px 20px; margin: 24px 0; background: #f8fafc; color: #475569; font-style: italic; border-radius: 4px; }
    ul, ol { padding-left: 24px; margin: 16px 0; }
    li { margin-bottom: 8px; }
    p { margin: 16px 0; }
    a { color: #4f46e5; text-decoration: underline; }
    hr { border: 0; border-top: 1px solid #e2e8f0; margin: 32px 0; }
    @media print { body { max-width: 100%; margin: 0; padding: 12mm; } }
  </style>
</head>
<body>
  <header style="margin-bottom: 32px; border-bottom: 1px solid #e2e8f0; padding-bottom: 16px;">
    <p style="font-size: 12px; color: #64748b; margin: 0;">Synthesized Dossier • ${new Date().toLocaleDateString()}</p>
  </header>
  ${article.markdown
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
    .replace(/^\s*-\s+(.+)$/gm, '<li>$1</li>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
    .replace(/\n\n/g, '<p></p>')}
</body>
</html>`;
    downloadFile(htmlDoc, `${getSlug()}.html`, 'text/html;charset=utf-8');
  };

  const handlePrint = () => {
    window.print();
    setShowDownloadMenu(false);
  };

  const handleCopy = () => {
    if (!article) return;
    navigator.clipboard.writeText(article.markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getFriendlyProgressMessage = () => {
    const p = jobStatus?.progress ?? 10;
    if (p < 25) return 'Analyzing source documents...';
    if (p < 55) return 'Extracting core findings and theoretical evidence...';
    if (p < 75) return 'Correlating claims and resolving cross-study perspectives...';
    if (p < 95) return 'Composing verified executive research brief...';
    return 'Finalizing synthesized document...';
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-900/60 backdrop-blur-xs">
        <motion.div
          initial={{ opacity: 0, scale: 0.97, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.97, y: 12 }}
          className="w-full max-w-4xl bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh] text-slate-800"
          role="dialog"
          aria-label="Research Brief Synthesis"
        >
          {/* Header */}
          <div className="px-6 py-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-slate-900 text-white flex items-center justify-center">
                <Sparkles className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-base font-bold text-slate-900">Research Brief Synthesis</h2>
                <p className="text-xs text-slate-500">
                  {article 
                    ? 'Verified executive briefing generated across your selected corpus'
                    : `Synthesizing ${cards.length} selected source${cards.length === 1 ? '' : 's'} into a unified brief`}
                </p>
              </div>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              aria-label="Close dialog"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Modal Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {article ? (
              /* Elegantly Formatted Reading View */
              <div className="space-y-6">
                {/* Reading Toolbar */}
                <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs">
                  <div className="flex items-center gap-2">
                    {/* View Switcher: Formatted vs Source */}
                    <div className="flex items-center bg-white border border-slate-200 rounded-lg p-0.5 shadow-2xs">
                      <button
                        onClick={() => setViewMode('formatted')}
                        className={`px-3 py-1 rounded-md transition-colors flex items-center gap-1.5 font-medium ${
                          viewMode === 'formatted'
                            ? 'bg-slate-900 text-white'
                            : 'text-slate-600 hover:text-slate-900'
                        }`}
                      >
                        <FileText className="w-3.5 h-3.5" />
                        <span>Reading View</span>
                      </button>
                      <button
                        onClick={() => setViewMode('source')}
                        className={`px-3 py-1 rounded-md transition-colors flex items-center gap-1.5 font-medium ${
                          viewMode === 'source'
                            ? 'bg-slate-900 text-white'
                            : 'text-slate-600 hover:text-slate-900'
                        }`}
                      >
                        <FileCode className="w-3.5 h-3.5" />
                        <span>Markdown</span>
                      </button>
                    </div>

                    {/* Font Size Selector */}
                    {viewMode === 'formatted' && (
                      <div className="flex items-center bg-white border border-slate-200 rounded-lg p-0.5 text-[11px] shadow-2xs">
                        <button
                          onClick={() => setFontSize('sm')}
                          className={`px-2 py-1 rounded ${fontSize === 'sm' ? 'bg-slate-200 text-slate-900 font-bold' : 'text-slate-500'}`}
                          title="Compact text"
                        >
                          A-
                        </button>
                        <button
                          onClick={() => setFontSize('base')}
                          className={`px-2 py-1 rounded ${fontSize === 'base' ? 'bg-slate-200 text-slate-900 font-bold' : 'text-slate-500'}`}
                          title="Standard text"
                        >
                          A
                        </button>
                        <button
                          onClick={() => setFontSize('lg')}
                          className={`px-2 py-1 rounded ${fontSize === 'lg' ? 'bg-slate-200 text-slate-900 font-bold' : 'text-slate-500'}`}
                          title="Large text"
                        >
                          A+
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Actions & Multi-Format Download Menu */}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleCopy}
                      className="px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-100 rounded-lg text-slate-700 font-medium flex items-center gap-1.5 transition-colors shadow-2xs"
                    >
                      {copied ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{copied ? 'Copied' : 'Copy Text'}</span>
                    </button>

                    {/* Download Dropdown */}
                    <div className="relative">
                      <button
                        onClick={() => setShowDownloadMenu(!showDownloadMenu)}
                        className="px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-lg font-medium flex items-center gap-1.5 transition-colors shadow-xs"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>Download</span>
                        <ChevronDown className="w-3 h-3 ml-0.5" />
                      </button>

                      {showDownloadMenu && (
                        <div className="absolute right-0 mt-1.5 w-48 bg-white border border-slate-200 rounded-xl shadow-xl py-1 z-30 text-xs">
                          <button
                            onClick={handleDownloadMarkdown}
                            className="w-full text-left px-3.5 py-2 hover:bg-slate-50 flex items-center gap-2 text-slate-700 font-medium"
                          >
                            <FileCode className="w-3.5 h-3.5 text-slate-400" />
                            <span>Markdown (.md)</span>
                          </button>
                          <button
                            onClick={handleDownloadHtml}
                            className="w-full text-left px-3.5 py-2 hover:bg-slate-50 flex items-center gap-2 text-slate-700 font-medium"
                          >
                            <Globe className="w-3.5 h-3.5 text-slate-400" />
                            <span>HTML Document (.html)</span>
                          </button>
                          <button
                            onClick={handleDownloadText}
                            className="w-full text-left px-3.5 py-2 hover:bg-slate-50 flex items-center gap-2 text-slate-700 font-medium"
                          >
                            <FileText className="w-3.5 h-3.5 text-slate-400" />
                            <span>Plain Text (.txt)</span>
                          </button>
                          <div className="border-t border-slate-100 my-1" />
                          <button
                            onClick={handlePrint}
                            className="w-full text-left px-3.5 py-2 hover:bg-slate-50 flex items-center gap-2 text-slate-700 font-medium"
                          >
                            <Printer className="w-3.5 h-3.5 text-slate-400" />
                            <span>Print / Save as PDF</span>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Article Content Area */}
                <div className="p-6 md:p-8 bg-white border border-slate-200 rounded-2xl shadow-xs">
                  {viewMode === 'formatted' ? (
                    <article className={`space-y-5 text-slate-800 leading-relaxed ${
                      fontSize === 'sm' ? 'text-xs' : fontSize === 'lg' ? 'text-base' : 'text-sm'
                    }`}>
                      {/* Formatted Markdown Parser */}
                      {article.markdown.split('\n\n').map((block, idx) => {
                        const trimmed = block.trim();
                        if (!trimmed) return null;

                        // Title H1
                        if (trimmed.startsWith('# ')) {
                          return (
                            <h1 key={idx} className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 border-b border-slate-200 pb-3">
                              {trimmed.replace(/^#\s+/, '')}
                            </h1>
                          );
                        }

                        // Heading 2
                        if (trimmed.startsWith('## ')) {
                          return (
                            <h2 key={idx} className="text-lg sm:text-xl font-bold text-slate-900 pt-4 border-t border-slate-100">
                              {trimmed.replace(/^##\s+/, '')}
                            </h2>
                          );
                        }

                        // Heading 3
                        if (trimmed.startsWith('### ')) {
                          return (
                            <h3 key={idx} className="text-base font-bold text-slate-800 pt-2">
                              {trimmed.replace(/^###\s+/, '')}
                            </h3>
                          );
                        }

                        // Blockquote / Executive Callout
                        if (trimmed.startsWith('>')) {
                          const quoteText = trimmed.replace(/^>\s*/gm, '');
                          return (
                            <div key={idx} className="p-4 rounded-xl bg-slate-50 border-l-4 border-slate-900 text-slate-700 italic space-y-1">
                              {quoteText.split('\n').map((line, lIdx) => (
                                <p key={lIdx} className="leading-relaxed">{line}</p>
                              ))}
                            </div>
                          );
                        }

                        // Divider
                        if (trimmed === '---') {
                          return <hr key={idx} className="border-t border-slate-200 my-4" />;
                        }

                        // Bullet list
                        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                          const items = trimmed.split('\n').map((l) => l.replace(/^[-*]\s+/, ''));
                          return (
                            <ul key={idx} className="space-y-1.5 pl-4 list-disc marker:text-slate-400">
                              {items.map((item, iIdx) => (
                                <li key={iIdx} className="leading-relaxed">{item}</li>
                              ))}
                            </ul>
                          );
                        }

                        // Numbered list
                        if (/^\d+\.\s+/.test(trimmed)) {
                          const items = trimmed.split('\n').map((l) => l.replace(/^\d+\.\s+/, ''));
                          return (
                            <ol key={idx} className="space-y-1.5 pl-4 list-decimal marker:text-slate-500 font-medium">
                              {items.map((item, iIdx) => (
                                <li key={iIdx} className="font-normal leading-relaxed">{item}</li>
                              ))}
                            </ol>
                          );
                        }

                        // Standard Paragraph
                        return (
                          <p key={idx} className="leading-relaxed text-slate-700">
                            {trimmed}
                          </p>
                        );
                      })}
                    </article>
                  ) : (
                    /* Raw Markdown Source */
                    <pre className="font-mono text-xs text-slate-800 bg-slate-50 p-4 rounded-xl border border-slate-200 overflow-x-auto whitespace-pre-wrap leading-relaxed select-all">
                      {article.markdown}
                    </pre>
                  )}
                </div>
              </div>
            ) : jobId ? (
              /* Ongoing Generation State with Sleek Minimalist Progress */
              <div className="py-12 px-6 max-w-xl mx-auto space-y-6 text-center">
                <div className="w-12 h-12 rounded-2xl bg-slate-900 text-white flex items-center justify-center mx-auto shadow-md">
                  <Loader2 className="w-6 h-6 animate-spin" />
                </div>

                <div className="space-y-2">
                  <h3 className="text-lg font-bold text-slate-900">
                    {getFriendlyProgressMessage()}
                  </h3>
                  <p className="text-xs text-slate-500">
                    Cross-referencing {cards.length} documents and composing a unified briefing.
                  </p>
                </div>

                {/* Sleek Progress Bar */}
                <div className="space-y-1.5">
                  <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden border border-slate-200">
                    <motion.div
                      className="h-full bg-slate-900 rounded-full"
                      initial={{ width: '8%' }}
                      animate={{ width: `${Math.max(10, Math.min(100, jobStatus?.progress ?? 15))}%` }}
                      transition={{ duration: 0.5, ease: 'easeOut' }}
                    />
                  </div>
                  <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
                    <span>Synthesizing</span>
                    <span>{jobStatus?.progress ?? 15}%</span>
                  </div>
                </div>
              </div>
            ) : (
              /* Pre-Launch Source Review */
              <div className="space-y-4 max-w-2xl mx-auto py-2">
                <div className="space-y-2">
                  <h3 className="text-sm font-bold text-slate-900">
                    Selected Source Documents ({cards.length})
                  </h3>
                  <p className="text-xs text-slate-500">
                    The synthesis engine will cross-reference findings and claims from these documents into a single executive brief.
                  </p>
                </div>

                <div className="max-h-56 overflow-y-auto space-y-2 border border-slate-200 rounded-xl p-3 bg-slate-50/50">
                  {cards.map((c, i) => (
                    <div 
                      key={c.id} 
                      className="p-2.5 rounded-lg bg-white border border-slate-200 flex items-center justify-between gap-3 text-xs shadow-2xs"
                    >
                      <div className="min-w-0">
                        <span className="font-semibold text-slate-900 block truncate">
                          {i + 1}. {c.title}
                        </span>
                        <span className="text-[11px] text-slate-500 truncate block">
                          {c.domain} · By {c.author}
                        </span>
                      </div>
                      <span className="text-[11px] font-mono text-slate-400 shrink-0">
                        {c.readTime}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Error Message if any */}
            {errorMessage && (
              <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 flex items-start gap-2.5 text-rose-800 text-xs">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                <div>
                  <h5 className="font-bold text-rose-950">Notice</h5>
                  <p>{errorMessage}</p>
                </div>
              </div>
            )}
          </div>

          {/* Footer Controls */}
          <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
            <span className="text-xs text-slate-500">
              {article 
                ? `${cards.length} source documents referenced`
                : `${cards.length} documents queued`}
            </span>

            <div className="flex items-center gap-2">
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-lg bg-white border border-slate-200 hover:bg-slate-100 text-xs font-semibold text-slate-700 transition-colors"
              >
                {article ? 'Done' : 'Cancel'}
              </button>

              {!article && !jobId && (
                <button
                  onClick={handleStartSynthesis}
                  disabled={isSubmitting || cards.length === 0}
                  className="px-5 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-40 text-xs font-semibold text-white flex items-center gap-2 shadow-xs transition-colors"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Starting...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Synthesize Brief ({cards.length} Sources)</span>
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
