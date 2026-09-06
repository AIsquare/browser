import { useState, useMemo, useCallback } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { INITIAL_RESEARCH_CARDS } from './data/researchData';
import { ResearchCard, DeckMode } from './types';
import { VerticalCascadingHand } from './components/VerticalCascadingHand';
import { HorizontalRibbonDeck } from './components/HorizontalRibbonDeck';
import { CoverFlowDeck } from './components/CoverFlowDeck';
import { ReaderView } from './components/ReaderView';
import { LeftSidebar } from './components/LeftSidebar';
import { FloatingTray } from './components/FloatingTray';
import { feedbackFeedback } from './utils/haptics';

export default function App() {
  const [cards, setCards] = useState<ResearchCard[]>(INITIAL_RESEARCH_CARDS);
  const [keptCards, setKeptCards] = useState<ResearchCard[]>([]);
  const [discardedCards, setDiscardedCards] = useState<ResearchCard[]>([]);
  const [selectedCard, setSelectedCard] = useState<ResearchCard | null>(null);
  const [hoveredCard, setHoveredCard] = useState<ResearchCard | null>(null);
  
  const [mode, setMode] = useState<DeckMode>('vertical-cascade');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [hapticsEnabled, setHapticsEnabled] = useState<boolean>(true);
  const [soundEnabled, setSoundEnabled] = useState<boolean>(true);
  const [isSearchingSearX, setIsSearchingSearX] = useState<boolean>(false);
  const [searxStatus, setSearxStatus] = useState<{ connected: boolean; count: number; error: string | null } | null>(null);
  const [searxngUrl, setSearxngUrl] = useState<string>(() => {
    try {
      return localStorage.getItem('searxng_url') || 'http://localhost:8080/search';
    } catch {
      return 'http://localhost:8080/search';
    }
  });

  const handleUpdateSearxngUrl = useCallback((newUrl: string) => {
    setSearxngUrl(newUrl);
    try {
      localStorage.setItem('searxng_url', newUrl);
    } catch {
      // ignore
    }
  }, []);

  // Status message / toast notification
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'keep' | 'discard' } | null>(null);

  const showToast = useCallback((text: string, type: 'keep' | 'discard') => {
    setToastMessage({ text, type });
    setTimeout(() => {
      setToastMessage(null);
    }, 2200);
  }, []);

  // Filtered cards based on active category and chat search query
  const filteredCards = useMemo(() => {
    let result = cards;

    // Filter by Category
    if (selectedCategory !== 'All') {
      result = result.filter((c) => c.category === selectedCategory);
    }

    // Filter by Search Query across title, summary, domain, author, key findings, and tags
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter((c) => {
        return (
          c.title.toLowerCase().includes(q) ||
          c.summary.toLowerCase().includes(q) ||
          c.domain.toLowerCase().includes(q) ||
          c.author.toLowerCase().includes(q) ||
          c.category.toLowerCase().includes(q) ||
          c.tags.some((t) => t.toLowerCase().includes(q)) ||
          c.keyFindings.some((f) => f.toLowerCase().includes(q))
        );
      });
    }

    return result;
  }, [cards, selectedCategory, searchQuery]);

  // Categories list
  const categories = useMemo(() => {
    const set = new Set<string>();
    INITIAL_RESEARCH_CARDS.forEach((c) => set.add(c.category));
    return ['All', ...Array.from(set)];
  }, []);

  // Audio & haptic trigger helper
  const triggerSensory = useCallback(
    (type: 'slide' | 'snap' | 'keep' | 'discard') => {
      feedbackFeedback(type, soundEnabled, hapticsEnabled);
    },
    [soundEnabled, hapticsEnabled]
  );

  // Workflow Action: Keep / Select card
  const handleKeepCard = useCallback(
    (cardToKeep: ResearchCard) => {
      triggerSensory('keep');
      showToast(
        mode === 'vertical-cascade'
          ? `Archived "${cardToKeep.title.slice(0, 32)}..." into Deep Dive Tray`
          : mode === 'horizontal-ribbon'
          ? `Tagged "${cardToKeep.title.slice(0, 32)}..." to Approved Investigation`
          : `Saved "${cardToKeep.title.slice(0, 32)}..." into Research Stack Folder`,
        'keep'
      );

      // Add to kept
      setKeptCards((prev) => [cardToKeep, ...prev]);

      // Remove from active deck
      const remaining = cards.filter((c) => c.id !== cardToKeep.id);
      setCards(remaining);

      // If reader is open, instantly slide adjacent card into view!
      if (selectedCard && selectedCard.id === cardToKeep.id) {
        const remainingFiltered = remaining.filter(
          (c) => selectedCategory === 'All' || c.category === selectedCategory
        );
        if (remainingFiltered.length > 0) {
          const currentIndex = filteredCards.findIndex((c) => c.id === cardToKeep.id);
          const nextIndex = Math.min(currentIndex, remainingFiltered.length - 1);
          setSelectedCard(remainingFiltered[nextIndex]);
        } else {
          setSelectedCard(null);
        }
      }
    },
    [cards, filteredCards, mode, selectedCard, selectedCategory, showToast, triggerSensory]
  );

  // Workflow Action: Discard card
  const handleDiscardCard = useCallback(
    (cardToDiscard: ResearchCard) => {
      triggerSensory('discard');
      showToast(`Discarded "${cardToDiscard.title.slice(0, 32)}..." to Trash Bin`, 'discard');

      // Add to discarded
      setDiscardedCards((prev) => [cardToDiscard, ...prev]);

      // Remove from active deck
      const remaining = cards.filter((c) => c.id !== cardToDiscard.id);
      setCards(remaining);

      // If reader is open, instantly slide adjacent card into view!
      if (selectedCard && selectedCard.id === cardToDiscard.id) {
        const remainingFiltered = remaining.filter(
          (c) => selectedCategory === 'All' || c.category === selectedCategory
        );
        if (remainingFiltered.length > 0) {
          const currentIndex = filteredCards.findIndex((c) => c.id === cardToDiscard.id);
          const nextIndex = Math.min(currentIndex, remainingFiltered.length - 1);
          setSelectedCard(remainingFiltered[nextIndex]);
        } else {
          setSelectedCard(null);
        }
      }
    },
    [cards, filteredCards, selectedCard, selectedCategory, showToast, triggerSensory]
  );

  // Adjacent navigation inside Reader
  const handleNavigateAdjacent = useCallback(
    (direction: 'next' | 'prev') => {
      if (!selectedCard) return;
      const currentIndex = filteredCards.findIndex((c) => c.id === selectedCard.id);
      if (currentIndex === -1) return;

      const targetIndex = direction === 'next' ? currentIndex + 1 : currentIndex - 1;
      if (targetIndex >= 0 && targetIndex < filteredCards.length) {
        setSelectedCard(filteredCards[targetIndex]);
        triggerSensory('slide');
      }
    },
    [filteredCards, selectedCard, triggerSensory]
  );

  // Restore card from kept or discarded
  const handleRestoreCard = useCallback(
    (card: ResearchCard, from: 'kept' | 'discarded') => {
      if (from === 'kept') {
        setKeptCards((prev) => prev.filter((c) => c.id !== card.id));
      } else {
        setDiscardedCards((prev) => prev.filter((c) => c.id !== card.id));
      }
      setCards((prev) => [card, ...prev]);
      triggerSensory('slide');
      showToast(`Restored "${card.title.slice(0, 30)}..." back to active deck`, 'keep');
    },
    [showToast, triggerSensory]
  );

  // Reset entire deck to original 10 cards
  const handleResetDeck = useCallback(() => {
    setCards(INITIAL_RESEARCH_CARDS);
    setKeptCards([]);
    setDiscardedCards([]);
    setSelectedCard(null);
    setSearchQuery('');
    setSelectedCategory('All');
    triggerSensory('snap');
    showToast('Re-dealt all 10 cards to active deck', 'keep');
  }, [showToast, triggerSensory]);

  // Live SearXNG Metasearch execution
  const handleSearXNGSearch = useCallback(async (query: string) => {
    if (!query.trim()) return;
    setIsSearchingSearX(true);
    triggerSensory('slide');

    try {
      const res = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), limit: 20, searxngUrl }),
      });

      if (!res.ok) {
        throw new Error(`Server returned status ${res.status}`);
      }

      const data = await res.json();
      if (data.cards && data.cards.length > 0) {
        setCards(data.cards);
        setSelectedCard(null);
        setSearchQuery('');
        setSelectedCategory('All');
        setSearxStatus({ connected: data.searxngConnected, count: data.cards.length, error: data.error });
        triggerSensory('snap');
        showToast(`Loaded ${data.cards.length} results from SearXNG metasearch`, 'keep');
      } else {
        setSearxStatus({ connected: false, count: 0, error: data.error || 'No results found' });
      }
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : String(err);
      setSearxStatus({ connected: false, count: 0, error: errMsg });
    } finally {
      setIsSearchingSearX(false);
    }
  }, [searxngUrl, showToast, triggerSensory]);

  const currentCardIndex = selectedCard
    ? filteredCards.findIndex((c) => c.id === selectedCard.id)
    : -1;

  return (
    <div className="flex flex-col lg:flex-row w-screen h-screen overflow-hidden bg-white font-sans text-slate-800 antialiased">
      {/* Left Pane: Chat Search, Settings, and Compact Metrics */}
      <LeftSidebar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        currentMode={mode}
        onModeChange={(newMode) => {
          setMode(newMode);
          triggerSensory('snap');
        }}
        hapticsEnabled={hapticsEnabled}
        onToggleHaptics={() => setHapticsEnabled(!hapticsEnabled)}
        soundEnabled={soundEnabled}
        onToggleSound={() => setSoundEnabled(!soundEnabled)}
        totalFetched={filteredCards.length}
        totalKept={keptCards.length}
        totalDiscarded={discardedCards.length}
        selectedCategory={selectedCategory}
        onSelectCategory={(cat) => {
          setSelectedCategory(cat);
          triggerSensory('slide');
        }}
        categories={categories}
        onResetDeck={handleResetDeck}
        hoveredCard={hoveredCard}
        onSearXNGSearch={handleSearXNGSearch}
        isSearchingSearX={isSearchingSearX}
        searxStatus={searxStatus}
        searxngUrl={searxngUrl}
        onUpdateSearxngUrl={handleUpdateSearxngUrl}
      />

      {/* Right Pane: 3D Turntable / Deck Canvas */}
      <main className="relative flex-1 h-full overflow-hidden flex flex-col bg-slate-50/50 border-t lg:border-t-0 border-slate-200">
        {/* Active Deck Mode View */}
        <div className="relative w-full h-full">
          {mode === 'vertical-cascade' && (
            <VerticalCascadingHand
              cards={filteredCards}
              onSelectCard={(card) => {
                setSelectedCard(card);
                triggerSensory('snap');
              }}
              onHoverCard={setHoveredCard}
              onSoundTrigger={triggerSensory}
              onQuickKeep={handleKeepCard}
              onQuickDiscard={handleDiscardCard}
            />
          )}

          {mode === 'horizontal-ribbon' && (
            <HorizontalRibbonDeck
              cards={filteredCards}
              onSelectCard={(card) => {
                setSelectedCard(card);
                triggerSensory('snap');
              }}
              onHoverCard={setHoveredCard}
              onSoundTrigger={triggerSensory}
            />
          )}

          {mode === 'cover-flow' && (
            <CoverFlowDeck
              cards={filteredCards}
              onSelectCard={(card) => {
                setSelectedCard(card);
                triggerSensory('snap');
              }}
              onQuickSelectKeep={handleKeepCard}
              onQuickDiscard={handleDiscardCard}
              onHoverCard={setHoveredCard}
              onSoundTrigger={triggerSensory}
              researchStackCount={keptCards.length}
            />
          )}
        </div>

        {/* Full-Page Workflow: Unfurls directly inside right pane! */}
        <AnimatePresence mode="wait">
          {selectedCard && (
            <ReaderView
              card={selectedCard}
              mode={mode}
              totalCards={filteredCards.length}
              currentIndex={currentCardIndex}
              onKeep={handleKeepCard}
              onDiscard={handleDiscardCard}
              onClose={() => setSelectedCard(null)}
              onNavigateAdjacent={handleNavigateAdjacent}
            />
          )}
        </AnimatePresence>

        {/* Action Toast Feedback */}
        <AnimatePresence>
          {toastMessage && (
            <motion.div
              initial={{ opacity: 0, y: -20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -16, scale: 0.95 }}
              className={`fixed top-4 right-4 sm:right-8 z-50 px-4 py-2.5 rounded-xl shadow-lg border text-xs font-medium flex items-center gap-2 bg-white ${
                toastMessage.type === 'keep'
                  ? 'border-emerald-300 text-emerald-800'
                  : 'border-rose-300 text-rose-800'
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${toastMessage.type === 'keep' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
              <span>{toastMessage.text}</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Floating Glowing Tray & Trash Bin */}
        <FloatingTray
          keptCards={keptCards}
          discardedCards={discardedCards}
          mode={mode}
          onRestoreCard={handleRestoreCard}
          onSelectKeptCard={(card) => {
            setSelectedCard(card);
            triggerSensory('snap');
          }}
        />
      </main>
    </div>
  );
}
