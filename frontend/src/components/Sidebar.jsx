import React, { useState, useMemo } from 'react';

// Format relative time helper
function formatRelativeTime(timestamp) {
  if (!timestamp) return 'Recently';
  const now = Date.now();
  const diffMs = now - timestamp;
  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMinutes < 1) return 'Just now';
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  
  const d = new Date(timestamp);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export default function Sidebar({
  onClose,
  onNewChat,
  chatHistory = [],
  currentChatId,
  onSelectChat,
  onDeleteChat,
  onClearHistory,
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const [confirmClear, setConfirmClear] = useState(false);

  // Filter and group ONLY real user chat history
  const filteredChats = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return chatHistory;
    return chatHistory.filter((chat) => {
      const titleMatch = chat.title?.toLowerCase().includes(q);
      const msgMatch = chat.messages?.some(
        (m) =>
          typeof m.content === 'string' && m.content.toLowerCase().includes(q)
      );
      return titleMatch || msgMatch;
    });
  }, [chatHistory, searchQuery]);

  const groupedChats = useMemo(() => {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const yesterdayStart = todayStart - 86400000;
    const weekStart = todayStart - 86400000 * 7;

    const groups = {
      Today: [],
      Yesterday: [],
      'Previous 7 Days': [],
      Older: [],
    };

    filteredChats.forEach((chat) => {
      const ts = chat.timestamp || Date.now();
      if (ts >= todayStart) {
        groups['Today'].push(chat);
      } else if (ts >= yesterdayStart) {
        groups['Yesterday'].push(chat);
      } else if (ts >= weekStart) {
        groups['Previous 7 Days'].push(chat);
      } else {
        groups['Older'].push(chat);
      }
    });

    return groups;
  }, [filteredChats]);

  const hasRealChats = chatHistory.length > 0;
  const hasFilteredResults = filteredChats.length > 0;

  return (
    <aside
      className="w-[85vw] max-w-[320px] sm:w-[320px] lg:w-[300px] xl:w-[340px] h-full bg-white flex flex-col overflow-hidden relative border-r border-slate-200/90 calispec-grid-pattern shrink-0 select-none shadow-[2px_0_10px_rgba(15,23,42,0.03)]"
      data-purpose="chatbot-sidebar-container"
    >
      {/* Ambient subtle top glow */}
      <div className="pointer-events-none absolute -top-24 left-1/2 -translate-x-1/2 w-72 h-44 bg-calispec-200/40 rounded-full blur-3xl"></div>

      {/* BEGIN: HeaderSection (Logo removed) */}
      <header className="relative z-10 px-4 pt-3.5 pb-2.5 bg-white/95 backdrop-blur-md border-b border-slate-100 flex items-center justify-end shrink-0">
        {/* Close Sidebar Button */}
        <button
          aria-label="Close sidebar"
          className="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          data-purpose="close-sidebar-button"
          type="button"
          onClick={onClose}
          title="Collapse Sidebar"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24">
            <path d="M6 18L18 6M6 6l12 12" strokeLinecap="round" strokeLinejoin="round"></path>
          </svg>
        </button>
      </header>
      {/* END: HeaderSection */}

      {/* BEGIN: ActionArea */}
      <div className="px-4 pt-3.5 pb-2.5 flex flex-col gap-2.5 relative z-10 shrink-0">
        {/* Primary New Chat Button */}
        <button
          className="w-full flex items-center justify-between px-4 py-3 bg-gradient-to-r from-calispec-600 via-sky-600 to-calispec-500 hover:from-calispec-700 hover:to-sky-600 text-white rounded-2xl shadow-cali-primary active:scale-[0.99] transition-all duration-200 group"
          data-purpose="new-chat-action"
          type="button"
          onClick={onNewChat}
        >
          <div className="flex items-center gap-2.5">
            <svg className="w-5 h-5 text-white/95" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" strokeLinecap="round" strokeLinejoin="round"></path>
            </svg>
            <span className="font-bold text-sm tracking-wide">New Chat</span>
          </div>
          <div className="w-7 h-7 rounded-xl bg-white/20 group-hover:bg-white/30 flex items-center justify-center transition-colors">
            <svg className="w-4 h-4 text-white font-bold" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
              <path d="M12 4v16m8-8H4" strokeLinecap="round" strokeLinejoin="round"></path>
            </svg>
          </div>
        </button>

        {/* Quick Conversation Search Bar */}
        <div className="relative">
          <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" strokeLinecap="round" strokeLinejoin="round"></path>
            </svg>
          </span>
          <input
            className="w-full pl-9 pr-8 py-2 text-xs bg-slate-50 hover:bg-slate-100/70 focus:bg-white text-slate-800 placeholder-slate-400 rounded-xl border border-slate-200 focus:border-calispec-500 focus:ring-2 focus:ring-calispec-100 outline-none transition-all"
            placeholder="Search conversation history..."
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button
              type="button"
              className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600"
              onClick={() => setSearchQuery('')}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          )}
        </div>
      </div>
      {/* END: ActionArea */}

      {/* BEGIN: ChatHistoryFeed (Only Real User Conversations) */}
      <div className="flex-1 overflow-y-auto custom-scroll px-3 pb-6 space-y-4" data-purpose="chat-history-scroll-feed">
        {/* History Header Row */}
        <div className="flex items-center justify-between px-2 pt-1">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Conversations</span>
          {hasRealChats && (
            confirmClear ? (
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    onClearHistory();
                    setConfirmClear(false);
                  }}
                  className="text-[10px] font-bold text-red-600 hover:text-red-700 bg-red-50 px-2 py-0.5 rounded transition-colors"
                >
                  Confirm Clear
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmClear(false)}
                  className="text-[10px] text-slate-400 hover:text-slate-600"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                className="text-[11px] font-semibold text-slate-400 hover:text-red-500 transition-colors flex items-center gap-1 group"
                type="button"
                onClick={() => setConfirmClear(true)}
              >
                <svg className="w-3.5 h-3.5 text-slate-400 group-hover:text-red-500" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                  <path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" strokeLinecap="round" strokeLinejoin="round"></path>
                </svg>
                <span>Clear all</span>
              </button>
            )
          )}
        </div>

        {/* Real User Conversations by Group */}
        {hasRealChats ? (
          hasFilteredResults ? (
            Object.entries(groupedChats).map(([groupName, chats]) => {
              if (chats.length === 0) return null;
              const isToday = groupName === 'Today';
              return (
                <section key={groupName} className="space-y-1">
                  <h3
                    className={`text-[10px] font-bold uppercase tracking-wider px-2.5 mb-1.5 flex items-center gap-1.5 ${
                      isToday ? 'text-calispec-700/80' : 'text-slate-400'
                    }`}
                  >
                    {isToday && <span className="w-1.5 h-1.5 rounded-full bg-calispec-500"></span>}
                    {groupName}
                  </h3>

                  {chats.map((chat) => {
                    const isActive = currentChatId === chat.id;
                    const lastAssistantMsg = chat.messages
                      ?.slice()
                      .reverse()
                      .find((m) => m.role === 'assistant' && (m.text || m.content));
                    const subtitle =
                      lastAssistantMsg?.text?.slice(0, 48) ||
                      (chat.messages?.length > 1
                        ? `${chat.messages.length} messages in session`
                        : 'Conversation session');

                    return (
                      <article
                        key={chat.id}
                        onClick={() => onSelectChat(chat.id)}
                        className={`group relative flex items-center justify-between p-2.5 rounded-xl cursor-pointer transition-all ${
                          isActive
                            ? 'bg-calispec-50/90 border border-calispec-200/80 text-calispec-950 shadow-sm'
                            : 'hover:bg-slate-50 border border-transparent hover:border-slate-200/80 text-slate-700'
                        }`}
                      >
                        <div className="flex items-start gap-2.5 min-w-0 pr-2">
                          <div
                            className={`mt-0.5 w-6 h-6 rounded-lg flex items-center justify-center shrink-0 transition-colors ${
                              isActive
                                ? 'bg-calispec-600 text-white'
                                : 'bg-slate-100 text-slate-500 group-hover:bg-calispec-100 group-hover:text-calispec-600'
                            }`}
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24">
                              <path d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" strokeLinecap="round" strokeLinejoin="round"></path>
                            </svg>
                          </div>
                          <div className="min-w-0">
                            <h4
                              className={`text-xs truncate ${
                                isActive
                                  ? 'font-bold text-calispec-900 group-hover:text-calispec-950'
                                  : 'font-semibold text-slate-700 group-hover:text-calispec-700'
                              }`}
                            >
                              {chat.title || 'Untitled Chat'}
                            </h4>
                            <p
                              className={`text-[11px] truncate mt-0.5 ${
                                isActive ? 'text-calispec-700/80 font-normal' : 'text-slate-400'
                              }`}
                            >
                              {subtitle}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-1 shrink-0">
                          <span
                            className={`text-[10px] font-medium whitespace-nowrap ${
                              isActive ? 'text-calispec-600' : 'text-slate-400'
                            }`}
                          >
                            {formatRelativeTime(chat.timestamp)}
                          </span>
                          <button
                            aria-label="Delete chat"
                            className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-500 transition-all rounded hover:bg-slate-200/50"
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDeleteChat(chat.id);
                            }}
                            title="Delete conversation"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                              <path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </section>
              );
            })
          ) : (
            <div className="py-8 px-4 text-center">
              <p className="text-xs font-semibold text-slate-500">No matching chats</p>
              <p className="text-[11px] text-slate-400 mt-1">Try another search term</p>
            </div>
          )
        ) : (
          /* Empty state when the user has not started any conversations yet */
          <div className="py-12 px-4 text-center flex flex-col items-center justify-center">
            <div className="w-11 h-11 mb-3 rounded-2xl bg-sky-50 border border-sky-100 flex items-center justify-center text-sky-600 shadow-xs">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                <path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" strokeLinecap="round" strokeLinejoin="round"></path>
              </svg>
            </div>
            <p className="text-xs font-bold text-slate-700">No conversations yet</p>
            <p className="text-[11px] text-slate-400 mt-1 max-w-[200px] leading-relaxed">
              Your search and chat sessions will be automatically stored and listed here.
            </p>
          </div>
        )}
      </div>
      {/* END: ChatHistoryFeed */}
    </aside>
  );
}
