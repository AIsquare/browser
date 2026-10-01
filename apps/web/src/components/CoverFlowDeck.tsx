import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Sparkles, 
  ChevronLeft, 
  ChevronRight, 
  FolderDown, 
  Trash2, 
  Maximize2,
  Layers,
  BookOpen
} from 'lucide-react';
import { ResearchCard } from '../types';

interface CoverFlowDeckProps {
  cards: ResearchCard[];
  onSelectCard: (card: ResearchCard) => void;
  onQuickSelectKeep: (card: ResearchCard) => void;
  onQuickDiscard: (card: ResearchCard) => void;
  onHoverCard?: (card: ResearchCard | null) => void;
  onSoundTrigger?: (type: 'slide' | 'snap' | 'keep' | 'discard') => void;
  researchStackCount: number;
}

export function CoverFlowDeck({
  cards,
  onSelectCard,
  onQuickSelectKeep,
  onQuickDiscard,
  onHoverCard,
  onSoundTrigger,
  researchStackCount
}: CoverFlowDeckProps) {
  const [activeIndex, setActiveIndex] = useState<number>(0);
  const [isDroppingDown, setIsDroppingDown] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const wheelLockRef = useRef<boolean>(false);

  // Keep active index within bounds
  useEffect(() => {
    if (cards.length > 0 && activeIndex >= cards.length) {
      setActiveIndex(Math.max(0, cards.length - 1));
    }
  }, [cards.length, activeIndex]);

  const activeCard = cards[activeIndex] || null;

  // Mechanical slide snap navigation
  const snapTo = (newIndex: number) => {
    if (newIndex < 0 || newIndex >= cards.length || newIndex === activeIndex) return;
    setActiveIndex(newIndex);
    onSoundTrigger?.('snap');
  };

  // Snappy wheel listener: snaps 1 card at a time with crisp mechanical slide
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    if (wheelLockRef.current) return;

    const delta = e.deltaY;
    if (Math.abs(delta) > 25) {
      wheelLockRef.current = true;
      if (delta > 0 && activeIndex < cards.length - 1) {
        snapTo(activeIndex + 1);
      } else if (delta < 0 && activeIndex > 0) {
        snapTo(activeIndex - 1);
      }
      setTimeout(() => {
        wheelLockRef.current = false;
      }, 220);
    }
  };

  // Keyboard navigation Left/Right & Space/Enter
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT' || (e.target as HTMLElement)?.tagName === 'TEXTAREA') return;

      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        snapTo(activeIndex + 1);
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        snapTo(activeIndex - 1);
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        if (activeCard) {
          onSelectCard(activeCard);
        }
      } else if (e.key.toLowerCase() === 's' || e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (activeCard) {
          handleDropSelect();
        }
      } else if (e.key.toLowerCase() === 'd') {
        e.preventDefault();
        if (activeCard) {
          handleDiscard();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeIndex, cards.length, activeCard]);

  // Drop card into Research Stack folder below
  const handleDropSelect = () => {
    if (!activeCard || isDroppingDown) return;
    setIsDroppingDown(true);
    onSoundTrigger?.('keep');

    setTimeout(() => {
      onQuickSelectKeep(activeCard);
      setIsDroppingDown(false);
    }, 280);
  };

  const handleDiscard = () => {
    if (!activeCard) return;
    onSoundTrigger?.('discard');
    onQuickDiscard(activeCard);
  };

  return (
    <div
      ref={containerRef}
      onWheel={handleWheel}
      className="relative w-full h-full flex flex-col justify-between items-center overflow-hidden select-none bg-slate-50/70 p-4 sm:p-6"
      role="region"
      aria-label="3D Cover Flow Deck Tactile Turntable"
    >
      {/* Subtle light background ambient glow */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[550px] h-[350px] bg-indigo-50/80 rounded-full blur-3xl pointer-events-none" />

      {/* Top Header & Snapping Mode Indicator */}
      <div className="z-20 w-full max-w-4xl flex items-center justify-between text-xs text-slate-500 mb-1">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
          <span className="font-semibold text-slate-800">3D Cover Flow Deck</span>
          <span className="text-slate-300">•</span>
          <span className="text-slate-500">Horizontal Turntable</span>
        </div>

        <div className="flex items-center gap-2 text-[11px] text-slate-500">
          <span className="hidden sm:inline">Scroll or ← → snaps cards</span>
          <span className="font-mono bg-white px-2 py-0.5 rounded border border-slate-200 text-slate-700 shadow-sm">
            {cards.length > 0 ? `${activeIndex + 1} / ${cards.length}` : 'Empty'}
          </span>
        </div>
      </div>

      {/* Turntable 3D Cover Flow Stage */}
      <div 
        className="relative w-full max-w-4xl flex-1 flex items-center justify-center my-2"
        style={{ perspective: 1100 }}
      >
        {cards.length === 0 ? (
          <div className="text-center p-8 bg-white border border-slate-200 rounded-2xl shadow-sm text-slate-500 max-w-md">
            <Layers className="w-8 h-8 mx-auto text-slate-400 mb-2" />
            <h3 className="font-semibold text-slate-800 text-sm">All cards processed in Research Stack</h3>
            <p className="text-xs text-slate-400 mt-1">Use Re-deal in the top-left to start again.</p>
          </div>
        ) : (
          <div className="relative w-full h-[370px] sm:h-[400px] flex items-center justify-center">
            {cards.map((card, index) => {
              const diff = index - activeIndex;
              const isCenter = diff === 0;

              if (Math.abs(diff) > 4) return null;

              let rotateY = 0;
              let translateX = 0;
              let translateZ = 0;
              let scale = 1;
              let opacity = 1;
              let zIndex = 10;

              if (isCenter) {
                rotateY = 0;
                translateX = 0;
                translateZ = 55;
                scale = 1.04;
                opacity = 1;
                zIndex = 50;
              } else if (diff < 0) {
                rotateY = 46;
                translateX = diff * 125 - 65;
                translateZ = -Math.abs(diff) * 90;
                scale = Math.max(0.72, 0.92 - Math.abs(diff) * 0.06);
                opacity = Math.max(0.4, 0.9 - Math.abs(diff) * 0.18);
                zIndex = 40 - Math.abs(diff);
              } else {
                rotateY = -46;
                translateX = diff * 125 + 65;
                translateZ = -Math.abs(diff) * 90;
                scale = Math.max(0.72, 0.92 - Math.abs(diff) * 0.06);
                opacity = Math.max(0.4, 0.9 - Math.abs(diff) * 0.18);
                zIndex = 40 - Math.abs(diff);
              }

              return (
                <motion.div
                  key={card.id}
                  animate={
                    isCenter && isDroppingDown
                      ? {
                          y: 280,
                          scale: 0.45,
                          opacity: 0,
                          transition: { duration: 0.26, ease: 'easeIn' }
                        }
                      : {
                          x: translateX,
                          y: 0,
                          z: translateZ,
                          rotateY: rotateY,
                          scale: scale,
                          opacity: opacity,
                        }
                  }
                  transition={{
                    type: 'spring',
                    stiffness: 340,
                    damping: 30,
                  }}
                  onClick={() => {
                    if (isCenter) {
                      onSelectCard(card);
                    } else {
                      snapTo(index);
                    }
                  }}
                  onMouseEnter={() => onHoverCard?.(card)}
                  onMouseLeave={() => onHoverCard?.(null)}
                  style={{
                    position: 'absolute',
                    width: '320px',
                    height: '370px',
                    zIndex,
                    transformStyle: 'preserve-3d',
                    willChange: 'transform, opacity',
                  }}
                  className={`rounded-2xl p-5 border cursor-pointer select-none flex flex-col justify-between transition-colors bg-white ${
                    isCenter
                      ? 'border-indigo-400 shadow-[0_22px_45px_-12px_rgba(30,41,59,0.22),0_0_0_1px_rgba(99,102,241,0.25)] ring-2 ring-indigo-500/20'
                      : 'border-slate-200/90 shadow-[0_12px_28px_-8px_rgba(30,41,59,0.12)] hover:border-slate-300'
                  }`}
                  role="listitem"
                  tabIndex={isCenter ? 0 : -1}
                >
                  {/* Card top: Domain Icon & Match Score */}
                  <div className="flex items-center justify-between">
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

                  {/* Thumbnail Banner */}
                  <div className="relative rounded-xl overflow-hidden aspect-[16/9] my-2 bg-slate-100 border border-slate-200">
                    <img
                      src={card.thumbnailUrl}
                      alt={card.title}
                      referrerPolicy="no-referrer"
                      className="w-full h-full object-cover"
                    />
                    <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded text-[10px] font-mono bg-white/90 text-slate-700 border border-slate-200 shadow-sm backdrop-blur-sm">
                      {card.category}
                    </span>
                  </div>

                  {/* Title & summary */}
                  <div className="flex-1 flex flex-col justify-start">
                    <h3 className="text-sm font-bold text-slate-900 tracking-tight leading-snug line-clamp-2">
                      {card.title}
                    </h3>
                    <p className="mt-1 text-xs text-slate-600 line-clamp-2 leading-relaxed">
                      {card.summary}
                    </p>
                  </div>

                  {/* Center Card Click Affordance */}
                  {isCenter && (
                    <div className="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-indigo-600 font-medium">
                      <span className="flex items-center gap-1">
                        <BookOpen className="w-3.5 h-3.5" />
                        Click to Expand Reader
                      </span>
                      <span className="text-[10px] text-slate-400 font-mono">Space/Enter</span>
                    </div>
                  )}
                </motion.div>
              );
            })}
          </div>
        )}

        {/* Carousel Side Flank Buttons */}
        <button
          onClick={() => snapTo(activeIndex - 1)}
          disabled={activeIndex <= 0}
          className="absolute left-2 z-50 p-2.5 rounded-full bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 disabled:opacity-20 disabled:pointer-events-none transition-all shadow-md"
          aria-label="Previous card in turntable"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <button
          onClick={() => snapTo(activeIndex + 1)}
          disabled={activeIndex >= cards.length - 1}
          className="absolute right-2 z-50 p-2.5 rounded-full bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 disabled:opacity-20 disabled:pointer-events-none transition-all shadow-md"
          aria-label="Next card in turntable"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

      {/* Visible "Research Stack" Folder Below Center + Action Buttons */}
      <div className="z-20 w-full max-w-xl bg-white border border-slate-200 rounded-2xl p-4 flex flex-col sm:flex-row items-center justify-between gap-4 shadow-lg">
        {/* Research Stack Folder Dock Indicator */}
        <div className="flex items-center gap-3">
          <div className="relative w-11 h-11 rounded-xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 shadow-sm">
            <FolderDown className="w-5 h-5" />
            {researchStackCount > 0 && (
              <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-indigo-600 text-white font-bold text-[10px] flex items-center justify-center shadow-sm">
                {researchStackCount}
              </span>
            )}
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-bold text-slate-800">Research Stack Folder</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200 font-mono">
                {researchStackCount} Stored
              </span>
            </div>
            <p className="text-[11px] text-slate-500">
              Cards drop straight down into this folder when selected
            </p>
          </div>
        </div>

        {/* Action buttons for center card */}
        <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
          <button
            id="coverflow-select-button"
            onClick={handleDropSelect}
            disabled={!activeCard || isDroppingDown}
            className="flex-1 sm:flex-none px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs sm:text-sm rounded-xl shadow-sm active:scale-95 transition-all flex items-center justify-center gap-1.5 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
            title="Drop into Research Stack folder below (S / K)"
          >
            <FolderDown className="w-4 h-4" />
            <span>Select (Drop Down)</span>
            <kbd className="hidden md:inline-block ml-1 px-1.5 py-0.5 text-[10px] bg-indigo-700/50 rounded text-white">S</kbd>
          </button>

          <button
            id="coverflow-discard-button"
            onClick={handleDiscard}
            disabled={!activeCard}
            className="px-3 py-2 bg-slate-100 hover:bg-rose-50 hover:text-rose-600 text-slate-600 font-medium text-xs rounded-xl border border-slate-200 hover:border-rose-200 transition-all flex items-center gap-1"
            title="Discard this card (D)"
          >
            <Trash2 className="w-4 h-4" />
            <span className="hidden sm:inline">Discard</span>
          </button>
        </div>
      </div>
    </div>
  );
}
