import React, { useState, useRef, useEffect } from 'react';
import { 
  Layers, 
  Film, 
  Disc3, 
  Vibrate, 
  Volume2, 
  VolumeX, 
  RotateCcw, 
  Sparkles, 
  Sliders, 
  Search, 
  Send, 
  X, 
  Bot, 
  User, 
  BookmarkCheck, 
  Trash2, 
  Keyboard, 
  Check,
  Globe,
  Loader2,
  type LucideIcon
} from 'lucide-react';
import { DeckMode, ResearchCard } from '../types';

interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  count?: number;
}

interface LeftSidebarProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  currentMode: DeckMode;
  onModeChange: (mode: DeckMode) => void;
  hapticsEnabled: boolean;
  onToggleHaptics: () => void;
  soundEnabled: boolean;
  onToggleSound: () => void;
  totalFetched: number;
  totalKept: number;
  totalDiscarded: number;
  onResetDeck: () => void;
  selectedCategory: string;
  onSelectCategory: (category: string) => void;
  categories: string[];
  hoveredCard: ResearchCard | null;
  onSearXNGSearch?: (query: string) => Promise<void>;
  isSearchingSearX?: boolean;
  searxStatus?: { connected: boolean; count: number; error: string | null } | null;
  searxngUrl?: string;
  onUpdateSearxngUrl?: (url: string) => void;
}

export function LeftSidebar({
  searchQuery,
  onSearchChange,
  currentMode,
  onModeChange,
  hapticsEnabled,
  onToggleHaptics,
  soundEnabled,
  onToggleSound,
  totalFetched,
  totalKept,
  totalDiscarded,
  onResetDeck,
  selectedCategory,
  onSelectCategory,
  categories,
  hoveredCard,
  onSearXNGSearch,
  isSearchingSearX = false,
  searxStatus,
  searxngUrl = 'http://localhost:8080/search',
  onUpdateSearxngUrl,
}: LeftSidebarProps) {
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [inputVal, setInputVal] = useState(searchQuery);
  const [localSearxUrl, setLocalSearxUrl] = useState(searxngUrl);
  const [isTestingSearx, setIsTestingSearx] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      text: 'Welcome to Research Deck. Filter active papers in real-time or click "SearXNG" to crawl live web pages with concurrent headless rendering.',
      timestamp: 'Just now',
    }
  ]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Sync input value if parent changes searchQuery (e.g. reset)
  useEffect(() => {
    setInputVal(searchQuery);
  }, [searchQuery]);

  // Auto-scroll chat to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = (textToSend?: string) => {
    const q = (textToSend !== undefined ? textToSend : inputVal).trim();
    if (!q) return;

    // Set search query in app state
    onSearchChange(q);
    setInputVal('');

    const userMsg: Message = {
      id: String(Date.now()),
      sender: 'user',
      text: q,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    const assistantMsg: Message = {
      id: String(Date.now() + 1),
      sender: 'assistant',
      text: `Filtered active deck for "${q}". Showing matching cards in the turntable deck.`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
  };

  const handleExecuteSearXNGSearch = async (customQuery?: string) => {
    const q = (customQuery !== undefined ? customQuery : inputVal).trim();
    if (!q || !onSearXNGSearch) return;

    const userMsg: Message = {
      id: String(Date.now()),
      sender: 'user',
      text: `Crawling SearXNG for: "${q}"`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInputVal('');

    await onSearXNGSearch(q);

    const assistantMsg: Message = {
      id: String(Date.now() + 1),
      sender: 'assistant',
      text: `SearXNG metasearch completed. Dealt fresh cards into the 3D deck. Click any card to inspect or read the live page as-is.`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, assistantMsg]);
  };

  const handlePingSearxng = async () => {
    setIsTestingSearx(true);
    setTestResult(null);
    try {
      const res = await fetch('/api/test-searxng', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: localSearxUrl.trim() }),
      });
      const data = await res.json();
      setTestResult({
        success: !!data.connected,
        message: data.message || (data.connected ? 'Connected!' : 'Connection failed'),
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setTestResult({ success: false, message: `Failed to ping: ${msg}` });
    } finally {
      setIsTestingSearx(false);
    }
  };

  const handleSaveSearxUrl = () => {
    if (onUpdateSearxngUrl && localSearxUrl.trim()) {
      onUpdateSearxngUrl(localSearxUrl.trim());
    }
    handlePingSearxng();
  };

  const handleResetSearch = () => {
    onSearchChange('');
    setInputVal('');
    onSelectCategory('All');
    setMessages((prev) => [
      ...prev,
      {
        id: String(Date.now()),
        sender: 'assistant',
        text: 'Cleared search filters. Displaying all research papers.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }
    ]);
  };

  const handleQuickPrompt = (prompt: string) => {
    if (prompt === 'All') {
      handleResetSearch();
    } else {
      handleSendMessage(prompt);
    }
  };

  const modeOptions: { id: DeckMode; title: string; subtitle: string; icon: LucideIcon }[] = [
    {
      id: 'vertical-cascade',
      title: 'Vertical 3D Cover Flow',
      subtitle: 'Vertical 3D turntable with scrollable tilt & depth',
      icon: Layers,
    },
    {
      id: 'horizontal-ribbon',
      title: 'Horizontal Ribbon Deck',
      subtitle: 'Filmstrip dealing cards edge-to-edge',
      icon: Film,
    },
    {
      id: 'cover-flow',
      title: '3D Cover Flow (Horizontal)',
      subtitle: 'Tactile turntable with mechanical slide',
      icon: Disc3,
    },
  ];

  const quickChips = ['Quantum', 'Autonomous Agents', 'Robotics', 'Bio-Engineering', 'Neural Networks', 'All'];

  return (
    <aside 
      aria-label="Research chat search and controls" 
      className="w-full lg:w-[410px] shrink-0 bg-white border-r border-slate-200 flex flex-col justify-between overflow-hidden select-none text-slate-800"
    >
      {/* 1. Header with Title and Settings Icon */}
      <div className="p-4 sm:p-5 border-b border-slate-200 bg-white">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 shadow-xs">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-900 tracking-tight flex items-center gap-2">
                Research Deck
              </h1>
              <p className="text-[11px] text-slate-500">
                Live continuous reader & 3D turntable
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {/* Quick Re-deal button */}
            <button
              onClick={onResetDeck}
              className="p-2 rounded-xl text-slate-500 hover:text-slate-800 hover:bg-slate-100 text-xs flex items-center gap-1 transition-colors border border-transparent hover:border-slate-200"
              title="Reset and re-deal deck"
              aria-label="Re-deal deck"
            >
              <RotateCcw className="w-4 h-4" />
            </button>

            {/* Settings Modal Button */}
            <button
              onClick={() => setShowSettingsModal(true)}
              className="p-2 rounded-xl text-slate-600 hover:text-indigo-600 hover:bg-indigo-50 text-xs flex items-center gap-1.5 transition-colors border border-slate-200 shadow-xs"
              title="Open Settings"
              aria-label="Open Settings"
            >
              <Sliders className="w-4 h-4" />
              <span className="text-xs font-semibold hidden sm:inline">Settings</span>
            </button>
          </div>
        </div>

        {/* 2. Compact Deck Metrics Strip: Total fetched, Kept, Discarded */}
        <div className="mt-3 py-2 px-3 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5">
            <span className="text-slate-400 font-medium">Fetched:</span>
            <span className="font-bold text-slate-900 font-mono">{totalFetched}</span>
          </div>
          <div className="h-3.5 w-[1px] bg-slate-200" />
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            <span className="text-emerald-700 font-medium">Kept:</span>
            <span className="font-bold text-emerald-800 font-mono">{totalKept}</span>
          </div>
          <div className="h-3.5 w-[1px] bg-slate-200" />
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-rose-400" />
            <span className="text-rose-700 font-medium">Discarded:</span>
            <span className="font-bold text-rose-800 font-mono">{totalDiscarded}</span>
          </div>
        </div>
      </div>

      {/* 3. Search Chat Conversational Stream */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-50/40">
        {/* Active search chip indicator */}
        {searchQuery && (
          <div className="flex items-center justify-between bg-indigo-50 border border-indigo-200 rounded-lg px-3 py-1.5 text-xs text-indigo-900">
            <span className="flex items-center gap-1.5 truncate">
              <Search className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
              <span>Filtering by: <strong>&ldquo;{searchQuery}&rdquo;</strong></span>
            </span>
            <button
              onClick={handleResetSearch}
              className="ml-2 text-indigo-600 hover:text-indigo-900 font-medium flex items-center gap-0.5"
            >
              <X className="w-3.5 h-3.5" />
              <span>Clear</span>
            </button>
          </div>
        )}

        {/* Quick Suggestion Chips */}
        <div className="space-y-1.5">
          <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400 block">
            Suggested Topics
          </span>
          <div className="flex flex-wrap gap-1.5">
            {quickChips.map((chip) => (
              <button
                key={chip}
                onClick={() => handleQuickPrompt(chip)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                  searchQuery.toLowerCase() === chip.toLowerCase()
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'bg-white text-slate-600 hover:text-indigo-600 hover:bg-indigo-50/60 border border-slate-200'
                }`}
              >
                {chip}
              </button>
            ))}
          </div>
        </div>

        {/* Message bubbles */}
        <div className="space-y-3 pt-2">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-2.5 ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.sender === 'assistant' && (
                <div className="w-6 h-6 rounded-full bg-indigo-100 border border-indigo-200 flex items-center justify-center text-indigo-700 shrink-0 mt-0.5">
                  <Bot className="w-3.5 h-3.5" />
                </div>
              )}
              <div
                className={`max-w-[85%] rounded-2xl p-3 text-xs leading-relaxed ${
                  msg.sender === 'user'
                    ? 'bg-indigo-600 text-white shadow-xs rounded-br-xs'
                    : 'bg-white border border-slate-200 text-slate-700 shadow-xs rounded-bl-xs'
                }`}
              >
                <p>{msg.text}</p>
                <span
                  className={`text-[9px] block mt-1 ${
                    msg.sender === 'user' ? 'text-indigo-200 text-right' : 'text-slate-400'
                  }`}
                >
                  {msg.timestamp}
                </span>
              </div>
              {msg.sender === 'user' && (
                <div className="w-6 h-6 rounded-full bg-slate-200 border border-slate-300 flex items-center justify-center text-slate-700 shrink-0 mt-0.5">
                  <User className="w-3.5 h-3.5" />
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 4. Chat Search Input Box at Bottom */}
      <div className="p-3.5 sm:p-4 bg-white border-t border-slate-200">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSendMessage();
          }}
          className="relative flex items-center"
        >
          <div className="absolute left-3 text-slate-400 pointer-events-none">
            <Search className="w-4 h-4" />
          </div>
          <input
            type="text"
            value={inputVal}
            onChange={(e) => {
              setInputVal(e.target.value);
              // Live update filter as user types!
              onSearchChange(e.target.value);
            }}
            placeholder="Search papers, topics, authors..."
            className="w-full pl-9 pr-16 py-2.5 bg-slate-50 hover:bg-slate-100/70 focus:bg-white border border-slate-200 focus:border-indigo-500 rounded-xl text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all shadow-xs"
          />

          <div className="absolute right-1.5 flex items-center gap-1">
            {inputVal && !isSearchingSearX && (
              <button
                type="button"
                onClick={handleResetSearch}
                className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg"
                title="Clear input"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
            <button
              type="button"
              onClick={() => handleExecuteSearXNGSearch()}
              disabled={!inputVal.trim() || isSearchingSearX}
              className="px-2 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white text-[11px] font-medium transition-colors flex items-center gap-1 shadow-2xs"
              title="Crawl live web with SearXNG"
            >
              {isSearchingSearX ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Globe className="w-3.5 h-3.5" />
              )}
              <span className="hidden sm:inline">SearXNG</span>
            </button>
            <button
              type="submit"
              disabled={!inputVal.trim() || isSearchingSearX}
              className="p-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white transition-colors"
              title="Filter Active Deck"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </form>
        <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400 px-1">
          <span>Active mode: <strong>{currentMode === 'vertical-cascade' ? '3D Vertical' : currentMode === 'horizontal-ribbon' ? 'Ribbon' : '3D Cover Flow'}</strong></span>
          <button 
            onClick={() => setShowSettingsModal(true)}
            className="hover:text-indigo-600 underline font-medium"
          >
            Settings & SearXNG
          </button>
        </div>
      </div>

      {/* 5. Settings Modal */}
      {showSettingsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs">
          <div className="w-full max-w-md bg-white border border-slate-200 rounded-2xl shadow-2xl p-6 space-y-5 text-slate-800">
            {/* Settings Header */}
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <Sliders className="w-5 h-5 text-indigo-600" />
                <h2 className="text-base font-bold text-slate-900">Research Deck Settings</h2>
              </div>
              <button
                onClick={() => setShowSettingsModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Deck Archetype Switcher */}
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500 block">
                Deck Mode Archetype
              </label>
              <div className="space-y-2">
                {modeOptions.map((opt) => {
                  const Icon = opt.icon;
                  const isActive = currentMode === opt.id;
                  return (
                    <button
                      key={opt.id}
                      onClick={() => onModeChange(opt.id)}
                      className={`w-full text-left p-3 rounded-xl border transition-all flex items-start gap-3 ${
                        isActive
                          ? 'bg-indigo-50/70 border-indigo-300 ring-1 ring-indigo-500/20 text-slate-900'
                          : 'bg-white border-slate-200 hover:border-slate-300 text-slate-700 hover:bg-slate-50'
                      }`}
                    >
                      <div className={`p-2 rounded-lg mt-0.5 ${
                        isActive ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600'
                      }`}>
                        <Icon className="w-4 h-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold">{opt.title}</span>
                          {isActive && <Check className="w-3.5 h-3.5 text-indigo-600" />}
                        </div>
                        <p className="text-[11px] text-slate-500 mt-0.5">{opt.subtitle}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Sensory & Feedback Controls */}
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500 block">
                Tactile & Sensory Feedback
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={onToggleHaptics}
                  className={`p-2.5 rounded-xl border text-xs flex items-center justify-between transition-colors ${
                    hapticsEnabled
                      ? 'bg-indigo-50 border-indigo-300 text-indigo-900 font-semibold'
                      : 'bg-white border-slate-200 text-slate-500 hover:text-slate-800'
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <Vibrate className="w-4 h-4 text-indigo-600" />
                    Haptics
                  </span>
                  <span className="text-[10px] font-mono">{hapticsEnabled ? 'ON' : 'OFF'}</span>
                </button>

                <button
                  onClick={onToggleSound}
                  className={`p-2.5 rounded-xl border text-xs flex items-center justify-between transition-colors ${
                    soundEnabled
                      ? 'bg-indigo-50 border-indigo-300 text-indigo-900 font-semibold'
                      : 'bg-white border-slate-200 text-slate-500 hover:text-slate-800'
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    {soundEnabled ? (
                      <Volume2 className="w-4 h-4 text-indigo-600" />
                    ) : (
                      <VolumeX className="w-4 h-4 text-slate-400" />
                    )}
                    Click Audio
                  </span>
                  <span className="text-[10px] font-mono">{soundEnabled ? 'ON' : 'OFF'}</span>
                </button>
              </div>
            </div>

            {/* SearXNG & Agent Integration */}
            <div className="space-y-2.5 p-3.5 bg-slate-50 rounded-xl border border-slate-200 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-900 flex items-center gap-1.5">
                  <Globe className="w-4 h-4 text-emerald-600" />
                  SearXNG Metasearch Engine
                </span>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold ${
                  testResult?.success || searxStatus?.connected
                    ? 'bg-emerald-100 text-emerald-800'
                    : 'bg-slate-200 text-slate-600'
                }`}>
                  {testResult?.success || searxStatus?.connected ? 'ONLINE' : 'ACTIVE / FALLBACK'}
                </span>
              </div>
              <p className="text-[11px] text-slate-500 leading-relaxed">
                Connects to your local or remote SearXNG metasearch instance with automatic multi-page concatenation and concurrent Playwright parsing.
              </p>

              {/* URL Input & Actions */}
              <div className="space-y-1.5 pt-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block">
                  SearXNG Endpoint URL
                </label>
                <div className="flex items-center gap-1.5">
                  <input
                    type="text"
                    value={localSearxUrl}
                    onChange={(e) => setLocalSearxUrl(e.target.value)}
                    placeholder="http://localhost:8080/search"
                    className="flex-1 px-2.5 py-1.5 bg-white border border-slate-200 focus:border-indigo-500 rounded-lg text-xs font-mono text-slate-800 focus:outline-none focus:ring-1 focus:ring-indigo-500/20"
                  />
                  <button
                    type="button"
                    onClick={handlePingSearxng}
                    disabled={isTestingSearx || !localSearxUrl.trim()}
                    className="px-2.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-50 text-indigo-700 font-semibold rounded-lg text-[11px] border border-indigo-200 transition-colors flex items-center gap-1 shrink-0"
                  >
                    {isTestingSearx ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                    <span>Test</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleSaveSearxUrl}
                    className="px-2.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg text-[11px] transition-colors shrink-0"
                  >
                    Save
                  </button>
                </div>
              </div>

              {/* Ping diagnostic feedback */}
              {testResult && (
                <div className={`p-2 rounded-lg text-[11px] leading-snug ${
                  testResult.success
                    ? 'bg-emerald-50 border border-emerald-200 text-emerald-800'
                    : 'bg-amber-50 border border-amber-200 text-amber-800'
                }`}>
                  <p className="font-medium">{testResult.message}</p>
                  {!testResult.success && (
                    <p className="mt-1 text-[10px] text-amber-700">
                      Tip: Run <code>docker run -d -p 8080:8080 searxng/searxng</code> and ensure <code>formats: [json]</code> is enabled in your SearXNG settings.
                    </p>
                  )}
                </div>
              )}

              <div className="flex items-center justify-between pt-1 border-t border-slate-200/60">
                <span className="text-[11px] text-slate-500">Quick Test Query:</span>
                <button
                  type="button"
                  onClick={() => {
                    setShowSettingsModal(false);
                    handleExecuteSearXNGSearch('autonomous generative AI robotics');
                  }}
                  className="px-2.5 py-1 bg-white hover:bg-slate-100 text-indigo-600 border border-slate-200 rounded-lg text-[11px] font-medium transition-colors"
                >
                  Run Query
                </button>
              </div>
            </div>

            {/* Re-deal Action */}
            <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
              <button
                onClick={() => {
                  onResetDeck();
                  setShowSettingsModal(false);
                }}
                className="px-3 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium text-xs flex items-center gap-1.5 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Re-deal All 10 Papers</span>
              </button>

              <button
                onClick={() => setShowSettingsModal(false)}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs rounded-xl transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
