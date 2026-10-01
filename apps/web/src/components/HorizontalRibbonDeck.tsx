import React, { useRef, useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { 
  Sparkles, 
  ChevronLeft, 
  ChevronRight, 
  BookOpen, 
  ArrowRight,
  Layers
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

  const CARD_WIDTH = 290;
  const CARD_GAP = 20;
  const STEP = CARD_WIDTH + CARD_GAP;

  const maxScroll = Math.max(0, (cards.length - 2.5) * STEP);

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
      <div className="absolute top-1/2 left-1/3 -translate-y-1/2 w-[600px] h-[300px] bg-indigo-50/70 rounded-full blur-3xl pointer-events-none" />

      {/* Top Controls & Filmstrip header */}
      <div className="z-10 flex items-center justify-between w-full max-w-6xl mx-auto mb-2 text-xs text-slate-500">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
          <span className="font-semibold text-slate-800">Horizontal Ribbon Deck</span>
          <span className="text-slate-300">•</span>
          <span className="text-slate-500">Filmstrip dealing cards edge-to-edge</span>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[11px] text-slate-400 hidden sm:inline">
            Scroll wheel or drag sideways like dealing cards
          </span>
          <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-0.5 shadow-sm">
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
          <div className="mx-auto text-center p-8 bg-white border border-slate-200 rounded-2xl shadow-sm text-slate-500 max-w-md">
            <Layers className="w-8 h-8 mx-auto text-slate-400 mb-2" />
            <h3 className="font-semibold text-slate-800 text-sm">All ribbon cards triaged</h3>
            <p className="text-xs text-slate-400 mt-1">Use Re-deal in the top-left to restart.</p>
          </div>
        ) : (
          <motion.div
            ref={ribbonRef}
            className="flex items-stretch gap-5 px-6 cursor-grab active:cursor-grabbing"
            animate={{ x: -scrollX }}
            transition={{
              type: 'spring',
              stiffness: 300,
              damping: 30,
            }}
          >
            {cards.map((card) => (
              <motion.div
                key={card.id}
                whileHover={{ y: -6, scale: 1.015 }}
                transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                onClick={() => {
                  onSelectCard(card);
                  onSoundTrigger?.('snap');
                }}
                onMouseEnter={() => onHoverCard?.(card)}
                onMouseLeave={() => onHoverCard?.(null)}
                className="w-[280px] sm:w-[300px] shrink-0 flex flex-col justify-between bg-white border border-slate-200 hover:border-indigo-300 rounded-2xl p-4 shadow-md hover:shadow-xl hover:shadow-indigo-100/50 transition-all cursor-pointer group"
                role="listitem"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectCard(card);
                  }
                }}
              >
                {/* Card top: Domain Icon & Match Score */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center text-xs font-bold text-indigo-700">
                      {card.domainFavicon.slice(0, 3)}
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs text-slate-800 font-semibold truncate max-w-[130px]">
                        {card.domain}
                      </span>
                      <span className="text-[10px] text-slate-400 font-mono">
                        {card.readTime}
                      </span>
                    </div>
                  </div>

                  <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                    <Sparkles className="w-3 h-3 text-emerald-600" />
                    {card.matchScore}%
                  </span>
                </div>

                {/* Clean Summary Thumbnail */}
                <div className="relative rounded-xl overflow-hidden aspect-[16/10] mb-3 bg-slate-100 border border-slate-200">
                  <img
                    src={card.thumbnailUrl}
                    alt={card.title}
                    referrerPolicy="no-referrer"
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded text-[10px] font-mono bg-white/90 text-slate-700 border border-slate-200 shadow-sm backdrop-blur-sm">
                    {card.category}
                  </span>
                </div>

                {/* Title & Excerpt */}
                <div className="flex-1 flex flex-col justify-start">
                  <h3 className="text-sm font-bold text-slate-900 tracking-tight leading-snug line-clamp-2 group-hover:text-indigo-600 transition-colors">
                    {card.title}
                  </h3>
                  <p className="mt-1.5 text-xs text-slate-600 line-clamp-2 leading-relaxed">
                    {card.summary}
                  </p>
                </div>

                {/* Bottom Action Footer */}
                <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
                  <span className="text-[11px] text-slate-400 truncate max-w-[150px]">
                    {card.author}
                  </span>
                  <span className="text-indigo-600 font-medium flex items-center gap-1 group-hover:translate-x-0.5 transition-transform">
                    Pop Drawer <ArrowRight className="w-3 h-3" />
                  </span>
                </div>
              </motion.div>
            ))}
          </motion.div>
        )}
      </div>

      {/* Bottom Dealing Progress & Summary */}
      <div className="z-10 flex items-center justify-between w-full max-w-6xl mx-auto text-xs text-slate-400">
        <span className="font-mono text-[11px] text-slate-500">
          Dealing {cards.length} cards along filmstrip
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-slate-400">Filmstrip Position</span>
          <div className="w-32 h-1.5 bg-slate-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-500 transition-all duration-150"
              style={{ width: `${Math.min(100, Math.max(5, (scrollX / (maxScroll || 1)) * 100))}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
