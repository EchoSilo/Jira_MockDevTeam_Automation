import { Header } from '@/components/common';
import { PMSelector, ChatContainer } from '@/components/chat';

export function ChatPage() {
  return (
    <div className="min-h-screen flex flex-col">
      <Header title="Chat with PM" subtitle="Ask questions or request actions" />

      <div className="flex-1 flex flex-col max-w-4xl mx-auto w-full">
        {/* PM Selector */}
        <div className="p-4 border-b border-[var(--color-border)]">
          <PMSelector />
        </div>

        {/* Chat area */}
        <div className="flex-1 overflow-hidden">
          <ChatContainer />
        </div>
      </div>
    </div>
  );
}
