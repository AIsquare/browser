import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { 
  BookmarkCheck, 
  Trash2, 
  X, 
  ChevronLeft, 
  ChevronRight, 
  ExternalLink, 
  CheckCircle2, 
  Sparkles,
  Share2,
  Globe,
  BookOpen,
  Lock,
  RotateCw,
  Shield
} from 'lucide-react';
import { ResearchCard, DeckMode } from '../types';

interface ReaderViewProps {
  card: ResearchCard;
  mode: DeckMode;
  totalCards: number;
  currentIndex: number;
  onKeep: (card: ResearchCard) => void;
  onDiscard: (card: ResearchCard) => void;
  onClose: () => void;
  onNavigateAdjacent: (direction: 'next' | 'prev') => void;
}

export function ReaderView({
  card,
  mode,
  totalCards,
  currentIndex,
  onKeep,
  onDiscard,
  onClose,
  onNavigateAdjacent
}: ReaderViewProps) {
  const [activeTab, setActiveTab] = useState<'reader' | 'interactive'>('reader');
  const [copied, setCopied] = useState(false);
  const [iframeKey, setIframeKey] = useState(0);

  const targetUrl = card.rawUrl || (card.domain.startsWith('http') ? card.domain : `https://${card.domain}`);
  const proxyUrl = `/api/proxy-page?url=${encodeURIComponent(targetUrl)}`;

  // Keyboard navigation inside reader
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key.toLowerCase() === 'k' || e.key.toLowerCase() === 's') {
        e.preventDefault();
        onKeep(card);
      } else if (e.key.toLowerCase() === 'd' || e.key.toLowerCase() === 'x') {
        e.preventDefault();
        onDiscard(card);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        onNavigateAdjacent('next');
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        onNavigateAdjacent('prev');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [card, onClose, onKeep, onDiscard, onNavigateAdjacent]);

  const handleShare = () => {
    navigator.clipboard?.writeText?.(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getKeepButtonLabel = () => {
    if (mode === 'vertical-cascade') return 'Keep for Deep Dive';
    if (mode === 'horizontal-ribbon') return 'Tag to Approved Investigation';
    return 'Select for Research Stack';
  };

  const getKeepButtonSubtitle = () => {
    if (mode === 'vertical-cascade') return 'Animates to glowing tray & slides next card';
    if (mode === 'horizontal-ribbon') return 'Pins to stack dock & loads adjacent';
    return 'Drops into research folder & focuses next';
  };

  return (
    <motion.div
      key={`reader-${card.id}`}
      initial={{ opacity: 0, scale: 0.97, y: 12 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95, y: 16 }}
      transition={{ type: 'spring', stiffness: 350, damping: 30 }}
      className="absolute inset-2 sm:inset-4 z-40 bg-white border border-slate-200/90 rounded-2xl shadow-2xl flex flex-col overflow-hidden text-slate-900"
      role="dialog"
      aria-label={`Reader view for ${card.title}`}
    >
      {/* Top Action Bar */}
      <header className="px-5 py-3.5 bg-slate-50/80 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3 select-none">
        <div className="flex items-center gap-2.5">
          <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
            {card.matchScore}% Match
          </span>
          <span className="text-xs text-slate-500 font-mono hidden sm:inline-block">
            {currentIndex + 1} of {totalCards}
          </span>
          <div className="h-4 w-[1px] bg-slate-200 hidden sm:block" />
          <span className="text-xs text-slate-600 flex items-center gap-1 font-medium">
            <Globe className="w-3 h-3 text-slate-400" />
            {card.domain}
          </span>
        </div>

        {/* Primary Action Buttons & Dismissal */}
        <div className="flex items-center gap-2 ml-auto">
          {/* Keep / Select Button */}
          <button
            id="reader-keep-button"
            onClick={() => onKeep(card)}
            title={getKeepButtonSubtitle()}
            className="group relative px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-xs sm:text-sm rounded-xl shadow-sm active:scale-95 transition-all flex items-center gap-2 focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:outline-none"
          >
            <BookmarkCheck className="w-4 h-4 text-white" />
            <span>{getKeepButtonLabel()}</span>
            <kbd className="hidden md:inline-block ml-1 px-1.5 py-0.5 text-[10px] bg-emerald-700 rounded text-emerald-100">K</kbd>
          </button>

          {/* Discard Button */}
          <button
            id="reader-discard-button"
            onClick={() => onDiscard(card)}
            title="Drops into trash bin and slides next card"
            className="px-3.5 py-2 bg-slate-100 hover:bg-rose-50 hover:text-rose-600 text-slate-600 font-medium text-xs sm:text-sm rounded-xl border border-slate-200 hover:border-rose-200 active:scale-95 transition-all flex items-center gap-1.5 focus-visible:ring-2 focus-visible:ring-rose-400 focus-visible:outline-none"
          >
            <Trash2 className="w-4 h-4 text-slate-400 group-hover:text-rose-600" />
            <span>Discard</span>
            <kbd className="hidden md:inline-block ml-1 px-1.5 py-0.5 text-[10px] bg-slate-200 rounded text-slate-600">D</kbd>
          </button>

          <div className="h-5 w-[1px] bg-slate-200 mx-1" />

          {/* Adjacent navigation */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => onNavigateAdjacent('prev')}
              disabled={currentIndex <= 0}
              className="p-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-30 disabled:pointer-events-none transition-colors"
              title="Previous card (Left Arrow)"
              aria-label="Previous card"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => onNavigateAdjacent('next')}
              disabled={currentIndex >= totalCards - 1}
              className="p-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-30 disabled:pointer-events-none transition-colors"
              title="Next card (Right Arrow)"
              aria-label="Next card"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* Close Reader */}
          <button
            id="reader-close-button"
            onClick={onClose}
            className="p-2 rounded-lg text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition-colors ml-1"
            title="Close reader (Esc)"
            aria-label="Close reader"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Reader Mode Tabs */}
      <div className="px-6 py-2 bg-slate-50/50 border-b border-slate-200 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('reader')}
            className={`flex items-center gap-1.5 py-1 px-3 rounded-lg font-medium transition-all ${
              activeTab === 'reader'
                ? 'bg-white text-indigo-600 shadow-sm border border-slate-200'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            <span>Structured Synthesis</span>
          </button>
          <button
            onClick={() => setActiveTab('interactive')}
            className={`flex items-center gap-1.5 py-1 px-3 rounded-lg font-medium transition-all ${
              activeTab === 'interactive'
                ? 'bg-white text-indigo-600 shadow-sm border border-slate-200'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Globe className="w-3.5 h-3.5" />
            <span>Live Page (As-Is)</span>
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleShare}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors"
            title="Copy link"
          >
            {copied ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> : <Share2 className="w-3.5 h-3.5" />}
            <span>{copied ? 'Copied' : 'Share'}</span>
          </button>
          <a
            href={targetUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="flex items-center gap-1 px-2.5 py-1 rounded-md text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors"
            title={`Open ${targetUrl}`}
          >
            <span>External</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>

      {/* Scrollable Reader Body */}
      <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6">
        {activeTab === 'reader' ? (
          <div className="max-w-3xl mx-auto space-y-6">
            {/* Header / Meta */}
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="px-2.5 py-0.5 rounded font-mono bg-slate-100 text-slate-700 border border-slate-200">
                  {card.category}
                </span>
                <span className="text-slate-300">•</span>
                <span className="text-slate-500">{card.readTime}</span>
                <span className="text-slate-300">•</span>
                <span className="text-slate-500">{card.publishedDate}</span>
                <span className="text-slate-300">•</span>
                <span className="text-slate-700 font-medium">{card.institution}</span>
              </div>

              <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-900 leading-tight">
                {card.title}
              </h1>

              <p className="text-sm text-slate-500 flex items-center gap-2">
                <span>By</span>
                <span className="text-slate-800 font-semibold">{card.author}</span>
              </p>
            </div>

            {/* Thumbnail Banner */}
            <div className="relative rounded-xl overflow-hidden border border-slate-200 aspect-[21/9] bg-slate-100 shadow-sm">
              <img
                src={card.thumbnailUrl}
                alt={card.title}
                referrerPolicy="no-referrer"
                className="w-full h-full object-cover"
              />
              <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between text-xs text-slate-700">
                <span className="bg-white/90 backdrop-blur px-2.5 py-1 rounded-md border border-slate-200 shadow-sm font-medium">
                  Source: {card.domain}
                </span>
                <span className="bg-white/90 backdrop-blur px-2.5 py-1 rounded-md border border-slate-200 shadow-sm font-medium">
                  Peer-Reviewed Dossier
                </span>
              </div>
            </div>

            {/* Executive Abstract */}
            <section className="p-5 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Executive Synthesis
              </h2>
              <p className="text-base text-slate-800 leading-relaxed">
                {card.summary}
              </p>
            </section>

            {/* Key Findings Checklist */}
            <section className="space-y-3">
              <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                Validated Empirical Findings
              </h2>
              <div className="grid gap-2.5">
                {card.keyFindings.map((finding, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl bg-white border border-slate-200 flex items-start gap-3 text-sm text-slate-700 shadow-sm"
                  >
                    <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600 mt-0.5">
                      0{idx + 1}
                    </span>
                    <span className="leading-relaxed">{finding}</span>
                  </div>
                ))}
              </div>
            </section>

            {/* Full Paper Text Sections */}
            <section className="space-y-4 pt-2">
              <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800">
                Deep Dive Analysis
              </h2>
              <div className="space-y-4 text-base text-slate-700 leading-relaxed font-normal">
                {card.fullArticle.map((para, i) => (
                  <p key={i} className="text-slate-700 leading-relaxed">
                    {para}
                  </p>
                ))}
              </div>
            </section>

            {/* Tags */}
            <div className="pt-4 border-t border-slate-200 flex flex-wrap gap-2">
              {card.tags.map((tag) => (
                <span
                  key={tag}
                  className="px-2.5 py-1 rounded-md text-xs bg-slate-100 text-slate-700 border border-slate-200"
                >
                  #{tag}
                </span>
              ))}
            </div>
          </div>
        ) : (
          /* Live As-Is Webpage View (Proxied to bypass X-Frame-Options) */
          <div className="max-w-5xl mx-auto h-[calc(100vh-280px)] min-h-[500px] flex flex-col bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            {/* Browser Navigation Bar */}
            <div className="px-4 py-2.5 bg-slate-100/90 border-b border-slate-200 flex items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-1.5 shrink-0">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-400 inline-block" />
                <span className="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block" />
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block" />
              </div>

              {/* URL address pill */}
              <div className="flex-1 max-w-2xl mx-auto flex items-center bg-white px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 font-mono text-[11px] shadow-2xs truncate">
                <Lock className="w-3 h-3 text-emerald-600 mr-2 shrink-0" />
                <span className="truncate select-all">{targetUrl}</span>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  onClick={() => setIframeKey((prev) => prev + 1)}
                  className="p-1.5 text-slate-500 hover:text-slate-800 hover:bg-slate-200/70 rounded-md transition-colors"
                  title="Reload live page"
                  aria-label="Reload live page"
                >
                  <RotateCw className="w-3.5 h-3.5" />
                </button>
                <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 hidden sm:inline-flex items-center gap-1">
                  <Shield className="w-3 h-3 text-emerald-600" />
                  Rendered As-Is
                </span>
                <a
                  href={targetUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-2.5 py-1 text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50 font-medium rounded-md transition-colors flex items-center gap-1 text-[11px]"
                  title="Open source in new browser tab"
                >
                  <span>Open Tab</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            </div>

            {/* Embedded Sandbox Iframe */}
            <div className="flex-1 w-full h-full relative bg-slate-50">
              <iframe
                key={iframeKey}
                src={proxyUrl}
                title={`Live as-is rendering of ${card.title}`}
                className="w-full h-full border-0 bg-white"
                sandbox="allow-same-origin allow-scripts allow-forms"
                referrerPolicy="no-referrer"
              />
            </div>
          </div>
        )}
      </div>

      {/* Bottom Sticky Action Strip */}
      <footer className="px-6 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500 select-none">
        <div className="flex items-center gap-4">
          <span className="hidden sm:inline">Shortcuts:</span>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-white rounded border border-slate-200 text-slate-700 shadow-xs font-mono">K</kbd> Keep
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-white rounded border border-slate-200 text-slate-700 shadow-xs font-mono">D</kbd> Discard
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-white rounded border border-slate-200 text-slate-700 shadow-xs font-mono">←/→</kbd> Skim
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-white rounded border border-slate-200 text-slate-700 shadow-xs font-mono">Esc</kbd> Close
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onKeep(card)}
            className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded-lg text-xs transition-colors flex items-center gap-1.5 shadow-sm"
          >
            <BookmarkCheck className="w-3.5 h-3.5" />
            <span>Keep & Next</span>
          </button>
          <button
            onClick={() => onDiscard(card)}
            className="px-3 py-1.5 bg-white hover:bg-rose-50 hover:text-rose-600 text-slate-700 border border-slate-200 rounded-lg text-xs transition-colors flex items-center gap-1.5"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Discard & Next</span>
          </button>
        </div>
      </footer>
    </motion.div>
  );
}
