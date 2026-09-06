import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  BookmarkCheck, 
  Trash2, 
  FolderArchive, 
  RotateCcw, 
  Download,
  X
} from 'lucide-react';
import { ResearchCard, DeckMode } from '../types';

interface FloatingTrayProps {
  keptCards: ResearchCard[];
  discardedCards: ResearchCard[];
  mode: DeckMode;
  onRestoreCard: (card: ResearchCard, from: 'kept' | 'discarded') => void;
  onSelectKeptCard: (card: ResearchCard) => void;
}

export function FloatingTray({
  keptCards,
  discardedCards,
  mode,
  onRestoreCard,
  onSelectKeptCard
}: FloatingTrayProps) {
  const [showKeptModal, setShowKeptModal] = useState(false);
  const [showTrashModal, setShowTrashModal] = useState(false);
  const [exportNotice, setExportNotice] = useState(false);

  const getTrayLabel = () => {
    if (mode === 'vertical-cascade') return 'Deep Dive Tray';
    if (mode === 'horizontal-ribbon') return 'Approved Investigation Dock';
    return 'Research Stack Folder';
  };

  const handleExportMarkdown = () => {
    if (keptCards.length === 0) return;
    const content = `# Curated Research Dossier\n\nGenerated via Interactive Research Decks\nTotal Kept: ${keptCards.length}\n\n` +
      keptCards.map((c, i) => (
        `### ${i + 1}. ${c.title}\n` +
        `- **Domain:** ${c.domain} (${c.matchScore}% match)\n` +
        `- **Author:** ${c.author} (${c.institution})\n` +
        `- **Summary:** ${c.summary}\n` +
        `- **Key Findings:**\n${c.keyFindings.map(f => `  * ${f}`).join('\n')}\n\n`
      )).join('---\n\n');

    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `research-dossier-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);

    setExportNotice(true);
    setTimeout(() => setExportNotice(false), 2500);
  };

  return (
    <>
      {/* Floating Bottom-Right Glowing Tray */}
      <aside aria-label="Deck collection trays" className="fixed bottom-4 right-4 sm:bottom-6 sm:right-6 z-30 flex items-center gap-3 select-none">
        {/* Discard Bin Trigger */}
        <button
          onClick={() => setShowTrashModal(true)}
          className="group relative p-3 rounded-2xl bg-white hover:bg-slate-50 border border-slate-200 hover:border-slate-300 shadow-lg text-slate-500 hover:text-rose-600 transition-all active:scale-95 flex items-center gap-2"
          title="Open Trash Bin / Discarded Cards"
          aria-label={`Discard bin (${discardedCards.length} discarded)`}
        >
          <Trash2 className="w-4 h-4" />
          {discardedCards.length > 0 && (
            <span className="text-xs font-mono font-bold text-rose-700 bg-rose-50 px-1.5 py-0.5 rounded border border-rose-200">
              {discardedCards.length}
            </span>
          )}
        </button>

        {/* The Saved/Deep-Dive Tray */}
        <motion.button
          onClick={() => setShowKeptModal(true)}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className={`group relative pl-4 pr-5 py-3 rounded-2xl border shadow-lg transition-all flex items-center gap-3 cursor-pointer bg-white ${
            keptCards.length > 0
              ? 'border-emerald-300 ring-2 ring-emerald-500/20 text-slate-800'
              : 'border-slate-200 text-slate-500 hover:text-slate-800'
          }`}
          title="View Kept Research Cards"
          aria-label={`${getTrayLabel()} (${keptCards.length} cards saved)`}
        >
          <div className="relative">
            <div className={`w-8 h-8 rounded-xl flex items-center justify-center transition-colors ${
              keptCards.length > 0 ? 'bg-emerald-50 text-emerald-600 border border-emerald-200' : 'bg-slate-100 text-slate-400'
            }`}>
              <BookmarkCheck className="w-5 h-5" />
            </div>
            {keptCards.length > 0 && (
              <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-emerald-600 text-white font-bold text-[9px] flex items-center justify-center shadow">
                {keptCards.length}
              </span>
            )}
          </div>

          <div className="text-left">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-bold text-slate-900 tracking-tight">
                {getTrayLabel()}
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 font-mono font-semibold border border-emerald-200">
                {keptCards.length} Kept
              </span>
            </div>
            <span className="text-[10px] text-slate-400 block">
              Click to inspect & export
            </span>
          </div>
        </motion.button>
      </aside>

      {/* Kept Cards Inspector Modal */}
      <AnimatePresence>
        {showKeptModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 16 }}
              className="w-full max-w-2xl bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] text-slate-800"
              role="dialog"
              aria-label={getTrayLabel()}
            >
              <div className="px-6 py-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center border border-emerald-200">
                    <FolderArchive className="w-4 h-4" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-slate-900">{getTrayLabel()}</h2>
                    <p className="text-xs text-slate-500">{keptCards.length} curated papers tagged for investigation</p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleExportMarkdown}
                    disabled={keptCards.length === 0}
                    className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 disabled:opacity-40 text-xs font-medium text-slate-700 flex items-center gap-1.5 transition-colors shadow-xs"
                    title="Export as Markdown dossier"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>{exportNotice ? 'Exported!' : 'Export .MD'}</span>
                  </button>
                  <button
                    onClick={() => setShowKeptModal(false)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-6 space-y-3">
                {keptCards.length === 0 ? (
                  <div className="text-center py-12 text-slate-400 space-y-2">
                    <BookmarkCheck className="w-8 h-8 mx-auto text-slate-300" />
                    <p className="text-sm font-medium text-slate-600">No cards kept in this stack yet.</p>
                    <p className="text-xs text-slate-400">
                      Use &quot;Keep for Deep Dive&quot; or &quot;Select&quot; in the active deck to pin items here.
                    </p>
                  </div>
                ) : (
                  keptCards.map((card) => (
                    <div
                      key={card.id}
                      className="p-4 rounded-xl bg-slate-50/70 border border-slate-200 hover:border-emerald-300 transition-colors flex items-start justify-between gap-4"
                    >
                      <div className="space-y-1.5 flex-1">
                        <div className="flex items-center gap-2 text-xs">
                          <span className="font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 font-semibold text-[10px]">
                            {card.matchScore}% Match
                          </span>
                          <span className="text-slate-300">•</span>
                          <span className="text-slate-500">{card.domain}</span>
                          <span className="text-slate-300">•</span>
                          <span className="text-slate-500">{card.category}</span>
                        </div>
                        <h4 
                          onClick={() => {
                            setShowKeptModal(false);
                            onSelectKeptCard(card);
                          }}
                          className="text-sm font-bold text-slate-900 hover:text-indigo-600 cursor-pointer transition-colors"
                        >
                          {card.title}
                        </h4>
                        <p className="text-xs text-slate-600 line-clamp-1">{card.summary}</p>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => {
                            setShowKeptModal(false);
                            onSelectKeptCard(card);
                          }}
                          className="px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 text-xs font-medium text-slate-700 transition-colors shadow-xs"
                        >
                          Read
                        </button>
                        <button
                          onClick={() => onRestoreCard(card, 'kept')}
                          className="p-1.5 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 text-slate-500 hover:text-slate-800 transition-colors shadow-xs"
                          title="Restore back to active deck"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Discarded Trash Bin Modal */}
      <AnimatePresence>
        {showTrashModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 16 }}
              className="w-full max-w-xl bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[80vh] text-slate-800"
              role="dialog"
              aria-label="Discarded Cards Bin"
            >
              <div className="px-6 py-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center border border-rose-200">
                    <Trash2 className="w-4 h-4" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-slate-900">Discard Bin</h2>
                    <p className="text-xs text-slate-500">{discardedCards.length} discarded items (can be restored)</p>
                  </div>
                </div>

                <button
                  onClick={() => setShowTrashModal(false)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-6 space-y-3">
                {discardedCards.length === 0 ? (
                  <div className="text-center py-10 text-slate-400 space-y-2">
                    <p className="text-sm font-medium text-slate-600">The trash bin is empty.</p>
                  </div>
                ) : (
                  discardedCards.map((card) => (
                    <div
                      key={card.id}
                      className="p-3.5 rounded-xl bg-slate-50/70 border border-slate-200 flex items-center justify-between gap-3"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-xs text-slate-400 flex items-center gap-2">
                          <span>{card.domain}</span>
                          <span>•</span>
                          <span>{card.category}</span>
                        </div>
                        <h4 className="text-sm font-medium text-slate-800 truncate">{card.title}</h4>
                      </div>

                      <button
                        onClick={() => onRestoreCard(card, 'discarded')}
                        className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 text-xs font-medium text-emerald-700 hover:text-emerald-800 flex items-center gap-1 transition-colors shadow-xs"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        <span>Restore</span>
                      </button>
                    </div>
                  ))
                )}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
