import React, { useRef, useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { 
  ChevronLeft, 
  ChevronRight, 
  ExternalLink,
  Layers,
  Lock,
  Globe,
  FileText
} from 'lucide-react';
import { ResearchCard } from '../types';

interface HorizontalRibbonDeckProps {
  cards: ResearchCard[];
  onSelectCard: (card: ResearchCard) => void;
  onHoverCard?: (card: ResearchCard | null) => void;
  onSoundTrigger?: (type: 'slide' | 'snap') => void;
}

export function HorizontalRibbonDeck({
  cards,
  onSelectCard,
  onHoverCard,
  onSoundTrigger
}: HorizontalRibbonDeckProps) {
  const ribbonRef = useRef<HTMLDivElement>(null);
  const [scrollX, setScrollX] = useState<number>(0);
  const lastSoundTimeRef = useRef<number>(0);

  const CARD_WIDTH = 440;
  const CARD_GAP = 24;
  const STEP = CARD_WIDTH + CARD_GAP;

  const maxScroll = Math.max(0, (cards.length - 2) * STEP);

  // Translate wheel scroll
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
    setScrollX((prev) => {
      const next = Math.max(0, Math.min(maxScroll, prev + delta * 0.8));
      return next;
    });

    const now = Date.now();
    if (now - lastSoundTimeRef.current > 120) {
      lastSoundTimeRef.current = now;
      onSoundTrigger?.('slide');
    }
  };

  // Keyboard navigation Left/Right
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT' || (e.target as HTMLElement)?.tagName === 'TEXTAREA') return;

      if (e.key === 'ArrowRight') {
        e.preventDefault();
        setScrollX((prev) => Math.min(maxScroll, prev + STEP));
        onSoundTrigger?.('slide');
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setScrollX((prev) => Math.max(0, prev - STEP));
        onSoundTrigger?.('slide');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [maxScroll, STEP, onSoundTrigger]);

  const scrollByStep = (direction: 'left' | 'right') => {
    setScrollX((prev) => {
      const target = direction === 'left' ? prev - STEP : prev + STEP;
      return Math.max(0, Math.min(maxScroll, target));
    });
    onSoundTrigger?.('slide');
  };

  return (
    <div
      onWheel={handleWheel}
      className="relative w-full h-full flex flex-col justify-between overflow-hidden select-none bg-slate-50/70 p-4 sm:p-6"
      role="region"
      aria-label="Horizontal Ribbon Deck Carousel"
    >
      {/* Background ambient lighting */}
      <div className="absolute top-1/2 left-1/3 -translate-y-1/2 w-[600px] h-[300px] bg-slate-100 rounded-full blur-3xl pointer-events-none" />

      {/* Top Controls & Filmstrip header */}
      <div className="z-10 flex items-center justify-between w-full max-w-7xl mx-auto mb-2 text-xs text-slate-500">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-900">Live Webpage Snapshot Deck</span>
          <span className="text-slate-300">·</span>
          <span className="text-slate-500">Readable content snapshots dealing edge-to-edge</span>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[11px] text-slate-400 hidden sm:inline">
            Scroll or drag to navigate snapshots
          </span>
          <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-0.5 shadow-xs">
            <button
              onClick={() => scrollByStep('left')}
              disabled={scrollX <= 0}
              className="p-1 rounded text-slate-600 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-30 transition-colors"
              aria-label="Scroll left"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => scrollByStep('right')}
              disabled={scrollX >= maxScroll}
              className="p-1 rounded text-slate-600 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-30 transition-colors"
              aria-label="Scroll right"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Filmstrip Track */}
      <div className="relative w-full flex-1 flex items-center overflow-hidden py-4">
        {/* Soft edge masking gradients */}
        <div className="absolute left-0 top-0 bottom-0 w-8 bg-gradient-to-r from-slate-50 to-transparent z-20 pointer-events-none" />
        <div className="absolute right-0 top-0 bottom-0 w-12 bg-gradient-to-l from-slate-50 to-transparent z-20 pointer-events-none" />

        {cards.length === 0 ? (
          <div className="mx-auto text-center p-8 bg-white border border-slate-200 rounded-2xl shadow-xs text-slate-500 max-w-md">
            <Layers className="w-8 h-8 mx-auto text-slate-400 mb-2" />
            <h3 className="font-semibold text-slate-800 text-sm">All cards triaged</h3>
            <p className="text-xs text-slate-400 mt-1">Search new topics or re-deal in the left sidebar.</p>
          </div>
        ) : (
          <motion.div
            ref={ribbonRef}
            className="flex items-stretch gap-6 px-6 cursor-grab active:cursor-grabbing"
            animate={{ x: -scrollX }}
            transition={{
              type: 'spring',
              stiffness: 300,
              damping: 30,
            }}
          >
            {cards.map((card) => {
              const displayUrl = card.rawUrl || `https://${card.domain}`;
              return (
                <motion.div
                  key={card.id}
                  whileHover={{ y: -6 }}
                  transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                  onClick={() => {
                    onSelectCard(card);
                    onSoundTrigger?.('snap');
                  }}
                  onMouseEnter={() => onHoverCard?.(card)}
                  onMouseLeave={() => onHoverCard?.(null)}
                  className="w-[380px] sm:w-[440px] md:w-[460px] shrink-0 flex flex-col justify-between bg-white border border-slate-200 hover:border-slate-400 rounded-2xl shadow-sm hover:shadow-xl transition-all cursor-pointer group overflow-hidden"
                  role="listitem"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelectCard(card);
                    }
                  }}
                >
                  {/* Browser Window Chrome Top Bar */}
                  <div className="px-4 py-2.5 bg-slate-100 border-b border-slate-200 flex items-center justify-between gap-2 text-xs">
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className="w-2.5 h-2.5 rounded-full bg-slate-300 group-hover:bg-rose-400 transition-colors" />
                      <span className="w-2.5 h-2.5 rounded-full bg-slate-300 group-hover:bg-amber-400 transition-colors" />
                      <span className="w-2.5 h-2.5 rounded-full bg-slate-300 group-hover:bg-emerald-400 transition-colors" />
                    </div>

                    {/* Realistic URL Address Bar */}
                    <div className="flex-1 max-w-[280px] mx-2 px-2.5 py-1 bg-white border border-slate-200 rounded-md text-[11px] font-mono text-slate-700 flex items-center gap-1.5 truncate shadow-2xs">
                      <Lock className="w-3 h-3 text-emerald-600 shrink-0" />
                      <span className="truncate">{displayUrl}</span>
                    </div>

                    <span className="text-[11px] font-medium text-slate-500 font-mono shrink-0">
                      {card.matchScore}% match
                    </span>
                  </div>

                  {/* Webpage Content Snapshot Body */}
                  <div className="p-5 flex-1 flex flex-col justify-between space-y-4">
                    {/* Header: Source metadata */}
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-xs text-slate-500">
                        <Globe className="w-3.5 h-3.5 text-slate-400" />
                        <span className="font-semibold text-slate-800">{card.institution || card.domain}</span>
                        <span aria-hidden="true">·</span>
                        <span>{card.category}</span>
                        <span aria-hidden="true">·</span>
                        <span>{card.readTime}</span>
                      </div>

                      {/* Webpage Headline */}
                      <h3 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight leading-snug group-hover:text-indigo-600 transition-colors line-clamp-2">
                        {card.title}
                      </h3>

                      <p className="text-xs text-slate-500 font-medium">
                        By {card.author} · {card.publishedDate}
                      </p>
                    </div>

                    {/* Webpage Summary "As-Is" */}
                    <p className="text-xs sm:text-sm text-slate-700 leading-relaxed line-clamp-3">
                      {card.summary}
                    </p>

                    {/* Key Findings Preview — readable without clicking! */}
                    {card.keyFindings && card.keyFindings.length > 0 && (
                      <div className="p-3 bg-slate-50 border border-slate-200/90 rounded-xl space-y-1.5">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                          <FileText className="w-3 h-3 text-slate-500" />
                          <span>Key Extracted Findings & Data</span>
                        </div>
                        <ul className="space-y-1 text-xs text-slate-700">
                          {card.keyFindings.slice(0, 2).map((finding, idx) => (
                            <li key={idx} className="flex items-start gap-1.5 line-clamp-2 leading-relaxed">
                              <span className="text-slate-400 font-mono text-[10px] mt-0.5">•</span>
                              <span>{finding}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Action Bar at Bottom of Webpage */}
                    <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
                      <span className="text-[11px] text-slate-400 font-mono truncate max-w-[200px]">
                        {card.domain}
                      </span>
                      <span className="text-slate-900 group-hover:text-indigo-600 font-semibold flex items-center gap-1.5 transition-colors">
                        <span>Open Live Page As-Is</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </span>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </motion.div>
        )}
      </div>

      {/* Bottom Dealing Progress & Summary */}
      <div className="z-10 flex items-center justify-between w-full max-w-7xl mx-auto text-xs text-slate-400">
        <span className="font-mono text-[11px] text-slate-500">
          Showing {cards.length} live webpage snapshots
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-slate-400">Deck Position</span>
          <div className="w-32 h-1.5 bg-slate-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-slate-900 transition-all duration-150"
              style={{ width: `${Math.min(100, Math.max(5, (scrollX / (maxScroll || 1)) * 100))}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
