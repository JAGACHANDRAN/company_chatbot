import React from 'react';

export default function Sidebar({
  isOpen,
  onClose,
  onNewChat,
  chatHistory = [],
  currentChatId,
  onSelectChat,
  onDeleteChat,
  onClearHistory,
}) {
  return (
    <>
      {/* Drawer Backdrop */}
      <div
        className={`fixed inset-0 bg-black/60 backdrop-blur-sm z-40 transition-opacity duration-300 ${
          isOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Left Sidebar Drawer: Chat History & New Chat */}
      <aside
        className={`fixed inset-y-0 left-0 w-80 bg-slate-950/95 border-r border-cyan-500/30 shadow-[10px_0_40px_rgba(0,0,0,0.85)] z-50 flex flex-col backdrop-blur-xl transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Drawer Header */}
        <div className="p-5 border-b border-slate-800/80 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-cyan-400">dataset</span>
            <span className="font-headline-xl text-sm font-semibold tracking-wide text-slate-100 uppercase">
              CALISPEC Console
            </span>
          </div>
          <button
            className="w-7 h-7 rounded-lg bg-slate-900 border border-slate-800 hover:border-cyan-500/40 flex items-center justify-center text-slate-400 hover:text-white transition-colors"
            onClick={onClose}
            type="button"
            title="Close Sidebar"
          >
            <span className="material-symbols-outlined text-base">close</span>
          </button>
        </div>

        {/* New Chat Button */}
        <div className="p-4">
          <button
            className="w-full flex items-center justify-between px-4 py-3 rounded-full bg-slate-900/90 border border-cyan-500/50 hover:border-cyan-400 text-slate-100 shadow-[0_0_15px_rgba(0,242,254,0.15)] hover:shadow-[0_0_20px_rgba(0,242,254,0.3)] transition-all group"
            onClick={() => {
              onNewChat();
              onClose();
            }}
            type="button"
          >
            <span className="font-medium text-xs tracking-wide">New Chat</span>
            <span className="w-6 h-6 rounded-full bg-cyan-500/20 group-hover:bg-cyan-400 text-cyan-300 group-hover:text-slate-950 flex items-center justify-center font-bold text-sm transition-all duration-200">
              +
            </span>
          </button>
        </div>

        {/* History List */}
        <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-4">
          <div>
            <div className="flex items-center justify-between px-2 mb-2">
              <span className="font-label-sm text-[10px] uppercase text-cyan-400/80 tracking-wider">
                Recent Metrology Sessions
              </span>
              {chatHistory.length > 0 && (
                <button
                  type="button"
                  onClick={onClearHistory}
                  className="text-[10px] text-slate-500 hover:text-rose-400 transition-colors"
                  title="Clear all sessions"
                >
                  Clear
                </button>
              )}
            </div>

            <div className="space-y-1.5">
              {chatHistory.length === 0 ? (
                <div className="p-4 text-center text-xs text-slate-500 rounded-xl bg-slate-900/40 border border-slate-800/60">
                  No previous sessions
                </div>
              ) : (
                chatHistory.map((item) => {
                  const isActive = currentChatId === item.id;
                  const promptCount = item.messages ? Math.floor(item.messages.length / 2) : 1;
                  return (
                    <div
                      key={item.id}
                      className={`group flex items-center justify-between p-2.5 rounded-xl border transition-all cursor-pointer ${
                        isActive
                          ? 'bg-cyan-950/40 border-cyan-500/50 text-slate-100 shadow-[0_0_12px_rgba(0,242,254,0.15)]'
                          : 'bg-slate-900/50 border-slate-800/80 hover:bg-slate-850 hover:border-cyan-500/30 text-slate-300'
                      }`}
                      onClick={() => {
                        onSelectChat(item.id);
                        onClose();
                      }}
                      title={item.title}
                    >
                      <div className="flex items-center gap-2.5 truncate flex-1 min-w-0 pr-1">
                        <span
                          className={`material-symbols-outlined text-base flex-shrink-0 ${
                            isActive ? 'text-cyan-400' : 'text-slate-500 group-hover:text-cyan-400'
                          }`}
                        >
                          chat_bubble
                        </span>
                        <div className="truncate">
                          <p className="text-xs font-medium truncate text-white">
                            {item.title}
                          </p>
                          <p className="text-[10px] font-label-sm text-slate-400">
                            {isActive ? 'Active Session' : `${promptCount} ${promptCount === 1 ? 'prompt' : 'prompts'}`}
                          </p>
                        </div>
                      </div>

                      <button
                        type="button"
                        className="opacity-0 group-hover:opacity-100 p-1 hover:text-rose-400 text-slate-500 transition-all flex-shrink-0"
                        title="Delete Session"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteChat(item.id);
                        }}
                      >
                        <span className="material-symbols-outlined text-sm">delete</span>
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
