import { useEffect, useRef } from 'react';
import { MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { SuggestedQuestions } from './SuggestedQuestions';
import { useChatStore } from '@/store';
import { api, ApiError } from '@/lib/api';
import type { ChatMessage as ChatMessageType } from '@/types';

const PM_NAMES: Record<string, string> = {
  alpha_pm: 'Sarah Chen',
  beta_pm: 'David Kim',
};

export function ChatContainer() {
  const {
    selectedPmId,
    conversations,
    currentConversationId,
    addMessage,
    startNewConversation,
    isSending,
    setIsSending,
  } = useChatStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const conversation = currentConversationId
    ? conversations[currentConversationId]
    : null;

  const messages = conversation?.messages || [];

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (content: string) => {
    let convId = currentConversationId;

    // Start new conversation if needed
    if (!convId || conversation?.pmId !== selectedPmId) {
      convId = startNewConversation(selectedPmId);
    }

    // Add user message
    const userMessage: ChatMessageType = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };
    addMessage(convId, userMessage);

    // Call the real PM chat API
    setIsSending(true);
    try {
      const response = await api.chat({
        pm_id: selectedPmId,
        message: content,
      });

      const pmResponse: ChatMessageType = {
        id: `msg_${Date.now() + 1}`,
        role: 'assistant',
        content: response.response,
        timestamp: new Date().toISOString(),
        pmName: response.pm_name,
        ticketsMentioned: response.tickets_mentioned,
      };
      addMessage(convId, pmResponse);
    } catch (error) {
      // Add error message as assistant response
      const errorMessage =
        error instanceof ApiError
          ? `Sorry, I couldn't connect to the server: ${error.message}`
          : 'Sorry, something went wrong. Please try again.';

      const errorResponse: ChatMessageType = {
        id: `msg_${Date.now() + 1}`,
        role: 'assistant',
        content: errorMessage,
        timestamp: new Date().toISOString(),
        pmName: PM_NAMES[selectedPmId],
      };
      addMessage(convId, errorResponse);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div
              className={cn(
                'flex h-16 w-16 items-center justify-center rounded-full mb-4',
                'bg-[var(--color-primary-muted)]'
              )}
            >
              <MessageSquare className="h-8 w-8 text-[var(--color-primary)]" />
            </div>
            <h3 className="text-lg font-medium text-[var(--color-text-primary)] mb-2">
              Chat with {PM_NAMES[selectedPmId]}
            </h3>
            <p className="text-sm text-[var(--color-text-muted)] mb-6 max-w-md">
              Ask about sprint status, team workload, blockers, or request actions
              like creating stories or prioritizing the backlog.
            </p>
            <SuggestedQuestions onSelect={handleSend} />
          </div>
        ) : (
          <>
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
            {isSending && (
              <div className="flex gap-3">
                <div
                  className={cn(
                    'flex h-8 w-8 items-center justify-center rounded-full',
                    'bg-[var(--color-surface-elevated)] border border-[var(--color-border)]'
                  )}
                >
                  <div className="flex gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-primary)] animate-bounce" />
                    <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-primary)] animate-bounce [animation-delay:150ms]" />
                    <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-primary)] animate-bounce [animation-delay:300ms]" />
                  </div>
                </div>
                <span className="text-sm text-[var(--color-text-muted)]">
                  {PM_NAMES[selectedPmId]} is typing...
                </span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Suggestions when conversation exists */}
      {messages.length > 0 && !isSending && (
        <div className="px-4 pb-2">
          <SuggestedQuestions onSelect={handleSend} />
        </div>
      )}

      {/* Input area */}
      <div className="p-4 border-t border-[var(--color-border)]">
        <ChatInput
          onSend={handleSend}
          isSending={isSending}
          placeholder={`Message ${PM_NAMES[selectedPmId]}...`}
        />
      </div>
    </div>
  );
}
