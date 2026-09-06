import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Sparkles, 
  ChevronUp, 
  ChevronDown, 
  BookOpen, 
  Check, 
  Trash2, 
  Layers,
  CornerDownRight,
  ArrowDown,
  ArrowUp
} from 'lucide-react';
import { ResearchCard } from '../types';

interface VerticalCascadingHandProps {
  cards: ResearchCard[];
  onSelectCard: (card: ResearchCard) => void;
  onHoverCard?: (card: ResearchCard | null) => void;
  onSoundTrigger?: (type: 'slide' | 'snap' | 'keep' | 'discard') => void;
  onQuickKeep?: (card: ResearchCard) => void;
  onQuickDiscard?: (card: ResearchCard) => void;
}

export function VerticalCascadingHand({
  cards,
  onSelectCard,
  onHoverCard,
  onSoundTrigger,
  onQuickKeep,
  onQuickDiscard
}: VerticalCascadingHandProps) {
  const [activeIndex, setActiveIndex] = useState<number>(0);
  const [bounceNotice, setBounceNotice] = useState<'head' | 'tail' | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const wheelLockRef = useRef<boolean>(false);

  // Keep active index within bounds when cards change
  useEffect(() => {
    if (cards.length > 0 && activeIndex >= cards.length) {
      setActiveIndex(Math.max(0, cards.length - 1));
    }
  }, [cards.length, activeIndex]);

  const activeCard = cards[activeIndex] || null;
  const remainingInTail = Math.max(0, cards.length - 1 - activeIndex);

  // Snap to specific card index with tactile feedback
  const snapTo = (newIndex: number) => {
    if (newIndex < 0) {
      setBounceNotice('head');
      onSoundTrigger?.('slide');
      setTimeout(() => setBounceNotice(null), 1200);
      return;
    }
    if (newIndex >= cards.length) {
      setBounceNotice('tail');
      onSoundTrigger?.('slide');
      setTimeout(() => setBounceNotice(null), 1200);
      return;
    }
    if (newIndex === activeIndex) return;
    setActiveIndex(newIndex);
    onSoundTrigger?.('snap');
  };

  // Smooth wheel listener with inertia dampening to prevent bumpy double-skips
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    if (wheelLockRef.current) return;

    const delta = e.deltaY;
    if (Math.abs(delta) > 22) {
      wheelLockRef.current = true;
      if (delta > 0) {
        if (activeIndex < cards.length - 1) {
          snapTo(activeIndex + 1);
        } else {
          // Bounded tail resistance
          setBounceNotice('tail');
          onSoundTrigger?.('slide');
          setTimeout(() => setBounceNotice(null), 900);
        }
      } else if (delta < 0) {
        if (activeIndex > 0) {
          snapTo(activeIndex - 1);
        } else {
          // Bounded head resistance
          setBounceNotice('head');
          onSoundTrigger?.('slide');
          setTimeout(() => setBounceNotice(null), 900);
        }
      }
      // 300ms lock matches transition duration so trackpad inertia doesn't trigger bumpy re-starts
      setTimeout(() => {
        wheelLockRef.current = false;
      }, 300);
    }
  };

  // Keyboard navigation Up/Down & Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT' || (e.target as HTMLElement)?.tagName === 'TEXTAREA') return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        snapTo(activeIndex + 1);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        snapTo(activeIndex - 1);
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        if (activeCard) {
          onSelectCard(activeCard);
        }
      } else if (e.key.toLowerCase() === 'k' || e.key.toLowerCase() === 's') {
        e.preventDefault();
        if (activeCard && onQuickKeep) {
          onQuickKeep(activeCard);
        }
      } else if (e.key.toLowerCase() === 'd') {
        e.preventDefault();
        if (activeCard && onQuickDiscard) {
          onQuickDiscard(activeCard);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeIndex, activeCard, cards.length, onQuickDiscard, onQuickKeep, onSelectCard]);

  // Update hovered card callback
  useEffect(() => {
    onHoverCard?.(activeCard);
  }, [activeCard, onHoverCard]);

  return (
    <div
      ref={containerRef}
      onWheel={handleWheel}
      className="relative w-full h-full flex flex-col items-center justify-between overflow-hidden select-none bg-slate-50/70 p-4 sm:p-6"
      role="region"
      aria-label="Vertical Cascading Deck with Tail"
    >
      {/* Subtle light background ambient glow */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[550px] h-[550px] bg-indigo-50/70 rounded-full blur-3xl pointer-events-none" />

      {/* Top Header Controls with Clear Deck Boundaries */}
      <div className="z-10 w-full max-w-2xl flex items-center justify-between text-xs text-slate-500 mb-1">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
          <span className="font-semibold text-slate-800">Vertical Cascading Deck</span>
          <span className="text-slate-300">•</span>
          <span className="px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-700 font-mono text-[11px] font-semibold shadow-xs">
            {activeIndex === 0
              ? 'Head of Deck (Card 1)'
              : activeIndex === cards.length - 1
              ? `Tail of Deck (Card ${cards.length})`
              : `Card ${activeIndex + 1} of ${cards.length}`}
          </span>
          {remainingInTail > 0 && (
            <span className="hidden sm:inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 font-medium">
              <ArrowUp className="w-2.5 h-2.5 text-indigo-600" />
              {remainingInTail} in tail above
            </span>
          )}
          {activeIndex > 0 && (
            <span className="hidden sm:inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200 font-medium">
              <Check className="w-2.5 h-2.5 text-emerald-600" />
              {activeIndex} sent back
            </span>
          )}
          {activeIndex === cards.length - 1 && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium">
              End of Tail
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[11px] text-slate-400 hidden sm:inline font-medium">
            Scroll or ↑/↓ to navigate cards
          </span>
          <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-0.5 shadow-xs">
            <button
              onClick={() => snapTo(activeIndex - 1)}
              disabled={activeIndex <= 0}
              className="p-1 rounded text-slate-600 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
              title="Previous card (Arrow Up)"
              aria-label="Previous card"
            >
              <ChevronUp className="w-4 h-4" />
            </button>
            <button
              onClick={() => snapTo(activeIndex + 1)}
              disabled={activeIndex >= cards.length - 1}
              className="p-1 rounded text-slate-600 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
              title="Next card in tail (Arrow Down)"
              aria-label="Next card"
            >
              <ChevronDown className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Main 3D Vertical Turntable Viewport with Physical Stacked Tail */}
      <div 
        className="relative w-full max-w-2xl flex-1 flex items-center justify-center my-1"
        style={{
          perspective: 1200,
          perspectiveOrigin: '50% 48%',
        }}
      >
        {cards.length === 0 ? (
          <div className="text-center p-8 bg-white border border-slate-200 rounded-2xl shadow-sm text-slate-500 max-w-md">
            <Layers className="w-8 h-8 mx-auto text-slate-400 mb-2" />
            <h3 className="font-semibold text-slate-800 text-sm">No cards remaining in active deck</h3>
            <p className="text-xs text-slate-400 mt-1">
              All items have been triaged. Use the Re-deal button in the top left to reload papers.
            </p>
          </div>
        ) : (
          <div className="relative w-full max-w-xl h-[310px] sm:h-[330px] flex items-center justify-center">
            {cards.map((card, index) => {
              const offset = index - activeIndex;

              // Visible range: up to 3 past cards (sent back), and up to 4 upcoming in upper tail
              if (offset < -3 || offset > 4) return null;

              const isActive = offset === 0;
              const isPast = offset < 0;
              const isTail = offset > 0;

              // Smooth harmonic transform calculations
              let yOffset = 0;
              let rotateX = 0;
              let zDepth = 0;
              let scale = 1;
              let opacity = 1;
              let zIndex = 50;

              if (isActive) {
                // Active Card / Head: Front and center in full view
                yOffset = 36;
                rotateX = 0;
                zDepth = 30;
                scale = 1;
                opacity = 1;
                zIndex = 50;
              } else if (isTail) {
                // Upper Tail: Evenly spaced above the head
                yOffset = 36 - offset * 68;
                rotateX = Math.min(offset * 3.5, 14);
                zDepth = -offset * 20;
                scale = Math.max(0.85, 1 - offset * 0.035);
                opacity = Math.max(0.3, 1 - offset * 0.16);
                zIndex = 50 - offset;
              } else if (isPast) {
                // Sent Back: Slips smoothly into depth tray
                const absOffset = Math.abs(offset);
                yOffset = 36 + absOffset * 52;
                rotateX = -absOffset * 5;
                zDepth = -absOffset * 35;
                scale = Math.max(0.86, 1 - absOffset * 0.04);
                opacity = Math.max(0.25, 1 - absOffset * 0.28);
                zIndex = 20 - absOffset;
              }

              return (
                <motion.div
                  key={card.id}
                  style={{
                    position: 'absolute',
                    width: '100%',
                    height: '100%',
                    zIndex,
                    transformStyle: 'preserve-3d',
                    willChange: 'transform, opacity',
                  }}
                  animate={{
                    y: yOffset,
                    rotateX,
                    z: zDepth,
                    scale,
                    opacity,
                  }}
                  transition={{
                    duration: 0.32,
                    ease: [0.25, 1, 0.5, 1],
                  }}
                  onClick={() => {
                    if (isActive) {
                      onSelectCard(card);
                    } else {
                      snapTo(index);
                    }
                  }}
                  className={`rounded-2xl p-5 sm:p-6 cursor-pointer bg-white border flex flex-col justify-between select-none ${
                    isActive
                      ? 'border-indigo-400 shadow-xl'
                      : isTail
                      ? 'border-slate-200 shadow-md'
                      : 'border-slate-200 shadow-xs'
                  }`}
                  role="listitem"
                  tabIndex={isActive ? 0 : -1}
                >
                  {/* Card Header */}
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <span className="w-6 h-6 rounded-md bg-slate-100 border border-slate-200 flex items-center justify-center text-[10px] font-bold text-slate-700">
                          {card.domainFavicon.slice(0, 3)}
                        </span>
                        <span className="text-xs font-semibold text-slate-700">
                          {card.domain}
                        </span>
                        <span className="text-slate-300">•</span>
                        <span className="text-[11px] text-slate-400 font-mono">
                          {card.readTime}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        {isTail ? (
                          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 flex items-center gap-1 shadow-2xs">
                            <ArrowDown className="w-3 h-3 text-indigo-600" />
                            Tail #{index + 1} • {card.matchScore}% Match
                          </span>
                        ) : isPast ? (
                          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200 flex items-center gap-1">
                            <Check className="w-3 h-3 text-emerald-600" />
                            Viewed #{index + 1}
                          </span>
                        ) : (
                          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                            <Sparkles className="w-3 h-3 text-emerald-600" />
                            {card.matchScore}% Match
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Title - clean and high contrast */}
                    <h3 className={`font-bold tracking-tight leading-snug line-clamp-2 ${
                      isActive 
                        ? 'text-base sm:text-lg text-slate-900' 
                        : isTail 
                        ? 'text-sm sm:text-base text-slate-800 font-semibold' 
                        : 'text-sm sm:text-base text-slate-600 font-medium'
                    }`}>
                      {card.title}
                    </h3>

                    {/* Summary text */}
                    <p className={`mt-1.5 text-xs sm:text-sm leading-relaxed ${
                      isTail 
                        ? 'text-slate-600 line-clamp-2' 
                        : isPast 
                        ? 'text-slate-500 line-clamp-1' 
                        : 'text-slate-600 line-clamp-3'
                    }`}>
                      {card.summary}
                    </p>
                  </div>

                  {/* Card Footer: Metadata & Quick Actions */}
                  <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-mono text-[10px]">
                        {card.category}
                      </span>
                      <span className="truncate max-w-[150px] text-[11px]">
                        {card.author}
                      </span>
                    </div>

                    {isActive ? (
                      <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                        {onQuickDiscard && (
                          <button
                            onClick={() => onQuickDiscard(card)}
                            className="px-2.5 py-1.5 rounded-lg border border-slate-200 hover:border-rose-300 hover:bg-rose-50 text-slate-500 hover:text-rose-600 text-xs font-medium flex items-center gap-1 transition-colors"
                            title="Discard card (D)"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span className="hidden sm:inline">Discard</span>
                          </button>
                        )}
                        {onQuickKeep && (
                          <button
                            onClick={() => onQuickKeep(card)}
                            className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium flex items-center gap-1 shadow-xs transition-colors"
                            title="Keep for Deep Dive (K / S)"
                          >
                            <Check className="w-3.5 h-3.5" />
                            <span className="hidden sm:inline">Keep</span>
                          </button>
                        )}
                        <button
                          onClick={() => onSelectCard(card)}
                          className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium flex items-center gap-1 shadow-xs transition-colors"
                          title="Open full reader view"
                        >
                          <BookOpen className="w-3.5 h-3.5" />
                          <span>Read</span>
                        </button>
                      </div>
                    ) : isTail ? (
                      <div className="flex items-center gap-1.5 text-indigo-600 font-semibold text-xs">
                        <CornerDownRight className="w-3.5 h-3.5" />
                        <span>Tail #{index + 1} • Click to Draw</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1 text-slate-500 hover:text-indigo-600 font-medium text-xs">
                        <ArrowUp className="w-3 h-3 text-indigo-600" />
                        <span>Viewed #{index + 1} • Click to Return</span>
                      </div>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}

        {/* Tactile Vertical Deck Spine / Tail Rail (Finite Deck Anchor) */}
        {cards.length > 1 && (
          <div 
            className="absolute right-1 sm:right-2 top-1/2 -translate-y-1/2 hidden md:flex flex-col items-center gap-1.5 bg-white/95 backdrop-blur-xs border border-slate-200 py-3 px-2 rounded-2xl shadow-sm z-30 select-none"
            aria-label="Deck spine navigator"
          >
            <span className="text-[9px] font-bold text-indigo-600 uppercase tracking-wider">Tail</span>
            <div className="flex flex-col-reverse items-center gap-1.5 my-1">
              {cards.map((c, i) => {
                const isCur = i === activeIndex;
                const isPast = i < activeIndex;
                return (
                  <button
                    key={c.id}
                    onClick={() => snapTo(i)}
                    className="group relative flex items-center justify-center p-0.5"
                    title={`Card #${i + 1}: ${c.title}`}
                    aria-label={`Jump to card ${i + 1}`}
                  >
                    <div className={`rounded-full transition-all duration-200 ${
                      isCur 
                        ? 'w-3.5 h-3.5 bg-indigo-600 ring-4 ring-indigo-100 shadow-xs' 
                        : isPast 
                        ? 'w-2 h-2 bg-slate-300 hover:bg-slate-400' 
                        : 'w-2 h-2 bg-indigo-300 hover:bg-indigo-400'
                    }`} />
                    <span className="absolute right-full mr-2 hidden group-hover:flex items-center px-2 py-1 rounded-md bg-slate-900 text-white text-[10px] font-mono whitespace-nowrap shadow-lg z-40 pointer-events-none">
                      #{i + 1} {c.title.slice(0, 22)}...
                    </span>
                  </button>
                );
              })}
            </div>
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">Head</span>
          </div>
        )}

        {/* Boundary Bounce Alert */}
        <AnimatePresence>
          {bounceNotice && (
            <motion.div
              initial={{ opacity: 0, scale: 0.9, y: bounceNotice === 'head' ? -12 : 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="absolute z-50 px-3.5 py-1.5 rounded-full bg-slate-900/90 text-white text-xs font-medium shadow-xl flex items-center gap-1.5"
            >
              {bounceNotice === 'head' ? (
                <span>At Start of Deck (Card 1)</span>
              ) : (
                <span>At End of Deck Tail (Card {cards.length})</span>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Visual Deck Tail Strip & Footer Status */}
      <div className="z-10 w-full max-w-2xl flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-slate-500 mt-1">
        {/* Physical Tail Queue summary */}
        <div className="flex items-center gap-2">
          {remainingInTail > 0 ? (
            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 font-semibold text-[11px]">
                <ArrowUp className="w-3 h-3 text-indigo-600" />
                <span>Upper Tail: <strong>{remainingInTail}</strong> card{remainingInTail > 1 ? 's' : ''} cascading above</span>
              </span>

              {/* Quick Jump Tail Badges */}
              <div className="hidden sm:flex items-center gap-1">
                {cards.slice(activeIndex + 1, activeIndex + 4).map((c, i) => (
                  <button
                    key={c.id}
                    onClick={() => snapTo(activeIndex + 1 + i)}
                    className="px-2 py-0.5 rounded-md bg-white hover:bg-indigo-50 hover:text-indigo-600 text-slate-600 border border-slate-200 text-[11px] font-mono transition-colors shadow-xs"
                    title={`Draw Card #${activeIndex + 2 + i}: ${c.title}`}
                  >
                    #{activeIndex + 2 + i}
                  </button>
                ))}
                {remainingInTail > 3 && (
                  <span className="text-[10px] text-slate-400 font-mono">+{remainingInTail - 3}</span>
                )}
              </div>
            </div>
          ) : (
            <span className="px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 font-semibold text-[11px] flex items-center gap-1">
              <Check className="w-3 h-3 text-emerald-600" />
              <span>Tail Reached • All {cards.length} Cards in View</span>
            </span>
          )}
        </div>

        {/* Progress bar and key shortcuts */}
        <div className="flex items-center gap-3 text-[11px] text-slate-400">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-slate-600 font-medium">
              {cards.length > 0 ? Math.round(((activeIndex + 1) / cards.length) * 100) : 0}%
            </span>
            <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 transition-all duration-200"
                style={{
                  width: cards.length > 0 ? `${((activeIndex + 1) / cards.length) * 100}%` : '0%',
                }}
              />
            </div>
          </div>
          <span className="hidden md:inline font-mono">K: Keep • D: Discard • Enter: Read</span>
        </div>
      </div>
    </div>
  );
}
