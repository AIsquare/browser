export interface ResearchCard {
  id: string;
  title: string;
  domain: string;
  domainFavicon: string;
  category: string;
  matchScore: number;
  author: string;
  institution: string;
  readTime: string;
  publishedDate: string;
  thumbnailUrl: string;
  summary: string;
  keyFindings: string[];
  fullArticle: string[];
  tags: string[];
  accentColor: string;
  badge: string;
  rawUrl?: string;
  html?: string;
}

export type DeckMode = 'vertical-cascade' | 'horizontal-ribbon' | 'cover-flow';

export interface DeckState {
  activeCards: ResearchCard[];
  keptCards: ResearchCard[];
  discardedCards: ResearchCard[];
  selectedCardId: string | null;
  mode: DeckMode;
  hapticsEnabled: boolean;
  soundEnabled: boolean;
}
