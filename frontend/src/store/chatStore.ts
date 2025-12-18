import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { ChatMessage, Conversation } from '@/types';

interface ChatState {
  selectedPmId: 'alpha_pm' | 'beta_pm';
  setSelectedPmId: (pmId: 'alpha_pm' | 'beta_pm') => void;
  conversations: Record<string, Conversation>;
  currentConversationId: string | null;
  setCurrentConversationId: (id: string | null) => void;
  addMessage: (conversationId: string, message: ChatMessage) => void;
  startNewConversation: (pmId: 'alpha_pm' | 'beta_pm') => string;
  isFloatingChatOpen: boolean;
  setFloatingChatOpen: (open: boolean) => void;
  isSending: boolean;
  setIsSending: (sending: boolean) => void;
}

const PM_NAMES: Record<string, string> = {
  alpha_pm: 'Sarah Chen',
  beta_pm: 'David Kim',
};

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      selectedPmId: 'alpha_pm',
      setSelectedPmId: (pmId) => set({ selectedPmId: pmId }),
      conversations: {},
      currentConversationId: null,
      setCurrentConversationId: (id) => set({ currentConversationId: id }),
      addMessage: (conversationId, message) =>
        set((state) => {
          const conversation = state.conversations[conversationId];
          if (!conversation) return state;
          return {
            conversations: {
              ...state.conversations,
              [conversationId]: {
                ...conversation,
                messages: [...conversation.messages, message],
              },
            },
          };
        }),
      startNewConversation: (pmId) => {
        const id = `conv_${Date.now()}`;
        set((state) => ({
          currentConversationId: id,
          conversations: {
            ...state.conversations,
            [id]: {
              id,
              pmId,
              pmName: PM_NAMES[pmId],
              messages: [],
              startedAt: new Date().toISOString(),
            },
          },
        }));
        return id;
      },
      isFloatingChatOpen: false,
      setFloatingChatOpen: (open) => set({ isFloatingChatOpen: open }),
      isSending: false,
      setIsSending: (sending) => set({ isSending: sending }),
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        conversations: state.conversations,
        currentConversationId: state.currentConversationId,
        selectedPmId: state.selectedPmId,
      }),
    }
  )
);
