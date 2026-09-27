import React, { useState, useEffect, useRef } from 'react';
import ChatMessage from './components/ChatMessage';
import Sidebar from './components/Sidebar';
import FileUploadModal from './components/FileUploadModal';
import DocumentInspectorModal from './components/DocumentInspectorModal';
import { sendChatMessage, fetchDatasets, deleteDatasetApi } from './api';

const STORAGE_KEY = 'calispec_chat_history_v2';
const ACTIVE_DATASET_KEY = 'calispec_active_dataset_id';

export default function App() {
  const [chatHistory, setChatHistory] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  const [currentChatId, setCurrentChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [inspectingDoc, setInspectingDoc] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [docsDropdownOpen, setDocsDropdownOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);

  // Datasets state
  const [datasets, setDatasets] = useState([]);
  const [activeDatasetId, setActiveDatasetId] = useState(() => {
    const saved = localStorage.getItem(ACTIVE_DATASET_KEY);
    return saved && saved !== 'default' ? saved : 'all';
  });

  const scrollViewRef = useRef(null);
  const docsPanelRef = useRef(null);
  const recognitionRef = useRef(null);

  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [isScrolled, setIsScrolled] = useState(false);

  const handleScroll = (e) => {
    const top = e.currentTarget.scrollTop;
    setIsScrolled(top > 80);
  };

  // Fetch uploaded datasets on mount
  useEffect(() => {
    loadDatasets();
  }, []);

  const loadDatasets = async () => {
    try {
      const res = await fetchDatasets();
      if (res?.datasets) {
        setDatasets(res.datasets);
      }
    } catch (err) {
      console.warn('Could not fetch datasets:', err);
    }
  };

  // Sync history to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(chatHistory));
    } catch (e) {
      console.error('Failed to save chat history to localStorage:', e);
    }
  }, [chatHistory]);

  // Sync active dataset to localStorage
  useEffect(() => {
    if (activeDatasetId) {
      localStorage.setItem(ACTIVE_DATASET_KEY, activeDatasetId);
    }
  }, [activeDatasetId]);

  // Auto-scroll when messages update
  useEffect(() => {
    if (scrollViewRef.current) {
      scrollViewRef.current.scrollTo({
        top: scrollViewRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [messages, loading]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (docsPanelRef.current && !docsPanelRef.current.contains(e.target)) {
        setDocsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleNewChat = () => {
    setCurrentChatId(null);
    setMessages([]);
    setInput('');
    setSidebarOpen(false);
    setIsScrolled(false);
    if (scrollViewRef.current) {
      scrollViewRef.current.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const handleSelectChat = (chatId) => {
    const chat = chatHistory.find((c) => c.id === chatId);
    if (chat) {
      setCurrentChatId(chat.id);
      setMessages(chat.messages || []);
      setInput('');
      setSidebarOpen(false);
    }
  };

  const handleDeleteChat = (chatId) => {
    setChatHistory((prev) => prev.filter((c) => c.id !== chatId));
    if (currentChatId === chatId) {
      handleNewChat();
    }
  };

  const handleClearHistory = () => {
    setChatHistory([]);
    handleNewChat();
  };

  // Handle successful dataset upload
  const handleUploadSuccess = (newDataset) => {
    loadDatasets();
    setActiveDatasetId('all');

    const announcementMsg = {
      id: `assistant-dataset-ready-${Date.now()}`,
      role: 'assistant',
      is_system_notice: true,
      text: `Your dataset is ready for private AI search.\n\n📄 File: ${newDataset.filename}\n📊 Records: ${newDataset.record_count?.toLocaleString()}\n🏷️ Columns: ${newDataset.fields?.join(', ')}\n\nThis file is now part of the searchable pool. All queries search across all uploaded datasets by default!`,
      dataset_name: newDataset.filename,
    };

    setMessages((prev) => [...prev, announcementMsg]);
  };

  const handleDeleteDataset = async (datasetIdToDelete) => {
    try {
      await deleteDatasetApi(datasetIdToDelete);
      if (activeDatasetId === datasetIdToDelete) {
        setActiveDatasetId('all');
      }
      loadDatasets();
    } catch (err) {
      alert(`Could not delete dataset: ${err.message}`);
    }
  };

  const toggleDictation = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setIsRecording(!isRecording);
      return;
    }

    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
    } else {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => setIsRecording(true);
      recognition.onresult = (event) => {
        const transcript = event.results?.[0]?.[0]?.transcript;
        if (transcript) {
          setInput((prev) => (prev ? `${prev} ${transcript}` : transcript));
        }
      };
      recognition.onerror = () => setIsRecording(false);
      recognition.onend = () => setIsRecording(false);

      recognitionRef.current = recognition;
      try {
        recognition.start();
      } catch {
        setIsRecording(false);
      }
    }
  };

  const handleSendMessage = async (textToSend) => {
    const query = (textToSend || input).trim();
    if (!query || loading) return;

    setInput('');

    const userMsg = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: query,
    };
    const loadingMsgId = `assistant-loading-${Date.now()}`;
    const loadingMsg = {
      id: loadingMsgId,
      role: 'assistant',
      loading: true,
    };

    const newMessages = [...messages, userMsg, loadingMsg];
    setMessages(newMessages);
    setLoading(true);

    let activeId = currentChatId;
    if (!activeId) {
      activeId = `chat-${Date.now()}`;
      setCurrentChatId(activeId);
    }

    try {
      const response = await sendChatMessage(query, activeDatasetId);
      const assistantMsg = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        loading: false,
        found: response.found,
        count: response.count,
        dataset_id: response.dataset_id,
        dataset_name: response.dataset_name,
        data: response.data,
        query_intent: response.query_intent,
        lookup_result: response.lookup_result,
        text: response.message,
      };

      const finalMessages = newMessages.map((msg) =>
        msg.id === loadingMsgId ? assistantMsg : msg
      );

      setMessages(finalMessages);

      setChatHistory((prev) => {
        const existingIdx = prev.findIndex((c) => c.id === activeId);
        const chatTitle = query.length > 38 ? query.substring(0, 38) + '...' : query;
        const chatItem = {
          id: activeId,
          title: chatTitle,
          timestamp: Date.now(),
          messages: finalMessages,
        };

        if (existingIdx >= 0) {
          const copy = [...prev];
          copy[existingIdx] = chatItem;
          return copy;
        } else {
          return [chatItem, ...prev];
        }
      });
    } catch (err) {
      const errorMsg = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        loading: false,
        error:
          err.message ||
          'Something went wrong while querying MongoDB. Please check database connection.',
      };

      const finalMessages = newMessages.map((msg) =>
        msg.id === loadingMsgId ? errorMsg : msg
      );

      setMessages(finalMessages);

      setChatHistory((prev) => {
        const existingIdx = prev.findIndex((c) => c.id === activeId);
        const chatTitle = query.length > 38 ? query.substring(0, 38) + '...' : query;
        const chatItem = {
          id: activeId,
          title: chatTitle,
          timestamp: Date.now(),
          messages: finalMessages,
        };

        if (existingIdx >= 0) {
          const copy = [...prev];
          copy[existingIdx] = chatItem;
          return copy;
        } else {
          return [chatItem, ...prev];
        }
      });
    } finally {
      setLoading(false);
    }
  };

  const activeDatasetObj = datasets.find((d) => d.dataset_id === activeDatasetId);
  const isAll = !activeDatasetId || activeDatasetId === 'all' || activeDatasetId === 'default';

  return (
    <div className="ambient-bg text-slate-100 font-body-md antialiased h-full flex flex-col overflow-hidden relative">
      {/* Grid Matrix Texture */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#0e22380d_1px,transparent_1px),linear-gradient(to_bottom,#0e22380d_1px,transparent_1px)] bg-[size:4rem_4rem] pointer-events-none z-0"></div>

      {/* Top Navigation Bar */}
      <header className="w-full px-6 py-4 flex items-center justify-between z-30 relative border-b border-cyan-950/40 bg-[#060d1a]/80 backdrop-blur-lg shrink-0">
        {/* Left Navigation Pill */}
        <div className="flex items-center">
          <button
            aria-label="Open Navigation Menu"
            className="flex items-center gap-2.5 px-4 py-1.5 rounded-full border border-slate-700/60 bg-[#060d1a]/80 hover:border-cyan-500/50 hover:bg-[#0c1a2d] transition-all text-xs font-medium tracking-wide text-slate-300 shadow-sm hover:shadow-[0_0_15px_rgba(56,189,248,0.3)]"
            onClick={() => setSidebarOpen(true)}
            type="button"
          >
            <span className="material-symbols-outlined text-sm text-cyan-400 group-hover:scale-110 transition-transform">
              menu
            </span>
            <span>Menu</span>
          </button>
        </div>


        {/* Center: Scroll-triggered sticky CALISPEC logo header (appears smoothly only when scrolled down) */}
        <div
          className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center cursor-pointer transition-all duration-300 ease-in-out z-20 ${
            isScrolled
              ? 'opacity-100 scale-100 translate-y-[-50%] pointer-events-auto'
              : 'opacity-0 scale-95 translate-y-[-40%] pointer-events-none'
          }`}
          onClick={handleNewChat}
          title="CALISPEC - Precision Metrology AI"
        >
          <div className="flex items-center gap-2.5 sm:gap-3 select-none">
            <div className="relative flex items-center justify-center w-8 h-8 sm:w-10 sm:h-10 flex-shrink-0">
              <svg viewBox="0 0 100 100" className="w-8 h-8 sm:w-10 sm:h-10 text-cyan-400 drop-shadow-[0_0_12px_rgba(0,242,254,0.95)]" fill="none" stroke="currentColor">
                <path d="M50 18a32 32 0 1 0 32 32" strokeWidth="8" strokeLinecap="round" strokeDasharray="3 7"></path>
                <path d="M50 8 v10 M50 82 v10 M8 50 h10 M82 50 h10 M20 20 l7 7 M73 73 l7 7 M20 80 l7 -7 M73 27 l7 -7" strokeWidth="7" strokeLinecap="round"></path>
                <circle cx="50" cy="50" r="8" fill="#f97316" stroke="none"></circle>
                <path d="M50 50 L68 34" stroke="#f97316" strokeWidth="4.5" strokeLinecap="round"></path>
              </svg>
            </div>
            <div className="flex flex-col justify-center">
              <div className="flex items-baseline gap-1 leading-none">
                <span className="font-headline-xl text-lg sm:text-xl font-bold tracking-widest text-cyan-400 drop-shadow-[0_0_12px_rgba(0,242,254,0.6)]">CALISPEC</span>
                <span className="text-[10px] font-bold text-cyan-300 font-label-sm">™</span>
              </div>
              <span className="text-[10px] text-amber-500 font-medium tracking-normal leading-tight mt-0.5">Proficient and Nimble</span>
            </div>
          </div>
        </div>

        {/* Right Quick Actions */}
        <div className="flex items-center gap-3">
          {/* Upload Docs Action */}
          <button
            className="flex items-center gap-2 px-4 py-1.5 rounded-full border border-slate-700/60 bg-[#060d1a]/80 hover:border-cyan-500/50 hover:bg-[#0c1a2d] transition-all text-xs font-medium text-slate-300 hover:text-white"
            onClick={() => setUploadModalOpen(true)}
            type="button"
          >
            <span className="material-symbols-outlined text-sm text-cyan-400">cloud_upload</span>
            <span>Upload Docs</span>
          </button>

          {/* Database Document Counter Pill & Dropdown container */}
          <div className="relative" ref={docsPanelRef}>
            <button
              className="flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-slate-700/60 bg-[#060d1a]/80 hover:border-cyan-500/50 hover:bg-[#0c1a2d] transition-all text-xs font-medium text-slate-300 hover:text-white"
              onClick={() => setDocsDropdownOpen(!docsDropdownOpen)}
              type="button"
            >
              <span className="material-symbols-outlined text-sm text-cyan-400">database</span>
              <span>DB Documents</span>
              <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-cyan-950/80 border border-cyan-800/60 text-cyan-300 ml-0.5">
                {datasets.length} Docs
              </span>
              <span
                className={`material-symbols-outlined text-[16px] text-slate-400 transition-transform duration-200 ${
                  docsDropdownOpen ? 'rotate-180' : ''
                }`}
              >
                expand_more
              </span>
            </button>

            {/* Dropdown Menu */}
            {docsDropdownOpen && (
              <div
                className="absolute right-0 mt-2.5 w-96 rounded-2xl bg-[#08111e]/95 border border-cyan-500/40 shadow-[0_12px_40px_rgba(0,0,0,0.85),0_0_25px_rgba(0,242,254,0.15)] backdrop-blur-xl p-4 z-50 animate-fadeIn"
                id="db-docs-panel"
              >
                <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800/80">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-cyan-400 text-base">folder_open</span>
                    <span className="text-xs font-semibold text-slate-100 tracking-wide uppercase font-headline-xl">
                      Indexed Repository
                    </span>
                  </div>
                  <span className="text-[10px] font-label-sm text-cyan-400/90 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-500/20">
                    Synced
                  </span>
                </div>

                <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                  {/* All Datasets Item */}
                  <div
                    className={`flex items-center justify-between p-2 rounded-xl transition-all cursor-pointer ${
                      isAll
                        ? 'bg-cyan-950/50 border border-cyan-500/50 shadow-[0_0_12px_rgba(0,242,254,0.15)]'
                        : 'bg-slate-900/60 hover:bg-slate-800/80 border border-slate-800 hover:border-cyan-500/40'
                    }`}
                    onClick={() => {
                      setActiveDatasetId('all');
                      setDocsDropdownOpen(false);
                    }}
                  >
                    <div className="flex items-center gap-2.5 truncate">
                      <span className="material-symbols-outlined text-cyan-400 text-lg flex-shrink-0">
                        layers
                      </span>
                      <div className="truncate">
                        <p className="text-xs font-medium text-slate-200 truncate">
                          All Uploaded Datasets (Default)
                        </p>
                        <p className="text-[10px] font-label-sm text-slate-400">
                          {datasets.length > 0
                            ? `Search across all ${datasets.length} files & Calispec database`
                            : 'Search Calispec MongoDB Collections'}
                        </p>
                      </div>
                    </div>
                    {isAll && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 font-label-sm">
                        Active
                      </span>
                    )}
                  </div>

                  {/* Individual Datasets */}
                  {datasets.map((d) => {
                    const isSelected = activeDatasetId === d.dataset_id;
                    const ext = d.original_type || d.filename?.split('.').pop() || 'csv';
                    const icon =
                      ext === 'pdf'
                        ? 'picture_as_pdf'
                        : ext === 'json'
                        ? 'data_object'
                        : ext === 'xml'
                        ? 'code'
                        : 'table_chart';
                    const iconColor =
                      ext === 'pdf'
                        ? 'text-rose-400'
                        : ext === 'json'
                        ? 'text-cyan-400'
                        : ext === 'xml'
                        ? 'text-amber-400'
                        : 'text-emerald-400';

                    return (
                      <div
                        key={d.dataset_id}
                        className={`group flex items-center justify-between p-2 rounded-xl transition-all cursor-pointer ${
                          isSelected
                            ? 'bg-cyan-950/50 border border-cyan-500/50 shadow-[0_0_12px_rgba(0,242,254,0.15)]'
                            : 'bg-slate-900/60 hover:bg-slate-800/80 border border-slate-800 hover:border-cyan-500/40'
                        }`}
                        onClick={() => {
                          setActiveDatasetId(d.dataset_id);
                          setDocsDropdownOpen(false);
                        }}
                      >
                        <div className="flex items-center gap-2.5 truncate flex-1 min-w-0 pr-1">
                          <span className={`material-symbols-outlined ${iconColor} text-lg flex-shrink-0`}>
                            {icon}
                          </span>
                          <div className="truncate">
                            <p className="text-xs font-medium text-slate-200 truncate">
                              {d.filename}
                            </p>
                            <p className="text-[10px] font-label-sm text-slate-500">
                              {d.record_count?.toLocaleString()} rows • .{ext}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          {isSelected && confirmDeleteId !== d.dataset_id && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950/70 border border-emerald-500/40 text-emerald-400 font-label-sm">
                              Active
                            </span>
                          )}
                          
                          {confirmDeleteId === d.dataset_id ? (
                            <div className="flex items-center gap-1 animate-fadeIn">
                              <button
                                type="button"
                                className="p-1 text-xs text-rose-400 hover:text-rose-300 bg-rose-950/50 rounded transition-all"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteDataset(d.dataset_id);
                                  setConfirmDeleteId(null);
                                }}
                              >
                                Confirm
                              </button>
                              <button
                                type="button"
                                className="p-1 text-xs text-slate-400 hover:text-slate-300 bg-slate-800 rounded transition-all"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setConfirmDeleteId(null);
                                }}
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className="opacity-0 group-hover:opacity-100 p-1 text-slate-500 hover:text-rose-400 transition-all"
                              title="Delete Dataset"
                              onClick={(e) => {
                                e.stopPropagation();
                                setConfirmDeleteId(d.dataset_id);
                              }}
                            >
                              <span className="material-symbols-outlined text-xs">delete</span>
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="mt-3 pt-2.5 border-t border-slate-800/80">
                  <button
                    type="button"
                    className="w-full flex items-center justify-center gap-2 py-2 rounded-xl bg-cyan-950/40 hover:bg-cyan-900/50 border border-cyan-500/30 text-xs font-medium text-cyan-300 transition-all shadow-sm"
                    onClick={() => {
                      setDocsDropdownOpen(false);
                      setUploadModalOpen(true);
                    }}
                  >
                    <span className="material-symbols-outlined text-sm">upload_file</span>
                    <span>Upload New Data File (.csv, .xlsx, .json, .xml, .txt)</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Slide-out Sidebar Drawer */}
      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={handleNewChat}
        chatHistory={chatHistory}
        currentChatId={currentChatId}
        onSelectChat={handleSelectChat}
        onDeleteChat={handleDeleteChat}
        onClearHistory={handleClearHistory}
      />

      {/* Main Central Area with Active Chat Conversation */}
      <main
        className="flex-1 overflow-y-auto flex flex-col items-center px-4 md:px-8 pt-2 pb-64 z-10 w-full"
        id="main-scroll-view"
        ref={scrollViewRef}
        onScroll={handleScroll}
      >
        <div className="w-full max-w-4xl flex flex-col items-center">
          {/* Futuristic HUD Emblem & Greeting Header */}
          <section className="flex flex-col items-center text-center w-full group/center select-none pt-2 pb-6">
            {/* Center Holographic Orb / Glow Visual System */}
            <div
              className="relative mb-5 flex items-center justify-center animate-float-center cursor-pointer"
              onClick={handleNewChat}
              title="Reset Chat Session"
            >
              {/* Ambient Multi-Color Volumetric Aura */}
              <div className="absolute -inset-24 bg-gradient-to-tr from-cyan-500/25 via-sky-500/20 to-orange-500/15 blur-3xl rounded-full pointer-events-none group-hover/center:blur-[60px] group-hover/center:opacity-100 transition-all duration-700 opacity-60"></div>
              {/* Rotating Conic Beam Sweep Effect */}
              <div className="absolute -inset-16 rounded-full animate-sweep-beam opacity-30 group-hover/center:opacity-75 transition-opacity duration-500 pointer-events-none"></div>
              {/* Concentric Kinetic Energy Rings */}
              <div className="absolute -inset-20 rounded-full border border-dashed border-cyan-400/20 animate-spin-clockwise pointer-events-none group-hover/center:border-cyan-400/50 group-hover/center:scale-105 transition-all duration-700"></div>
              <div className="absolute -inset-12 rounded-full border border-teal-400/30 animate-spin-counter pointer-events-none group-hover/center:border-teal-300/60 transition-all duration-700"></div>
              <div className="absolute -inset-6 rounded-full border border-cyan-300/40 animate-pulse-aura pointer-events-none"></div>
              {/* Orbital Particle Photons */}
              <div className="absolute w-2.5 h-2.5 rounded-full bg-cyan-300 shadow-[0_0_12px_#00f2fe] orbit-dot-1 pointer-events-none"></div>
              <div className="absolute w-2 h-2 rounded-full bg-orange-400 shadow-[0_0_10px_#f97316] orbit-dot-2 pointer-events-none"></div>

              {/* Seamless Futuristic HUD Display Pod for Logo */}
              <div className="relative z-10 px-8 py-3.5 sm:px-10 sm:py-4 rounded-3xl bg-slate-950/80 border border-cyan-500/40 backdrop-blur-2xl shadow-[0_0_35px_rgba(0,242,254,0.35),inset_0_0_20px_rgba(56,189,248,0.2)] group-hover/center:border-cyan-300 group-hover/center:shadow-[0_0_55px_rgba(0,242,254,0.65),inset_0_0_25px_rgba(0,242,254,0.35)] transition-all duration-500 flex items-center justify-center">
                <div className="relative max-w-[240px] sm:max-w-[300px] md:max-w-[340px] flex items-center justify-center overflow-hidden py-1 px-3">
                  <img
                    alt="CALISPEC - Proficient and Nimble"
                    className="w-full h-auto object-contain hologram-logo-dark"
                    src="https://lh3.googleusercontent.com/aida-public/AB6AXuBZSsmZYIs6iqsXtEmYVqi3yx5MJa2L1DBdHezpGWio05WYOnmy06Fv4SHmV6KzRd81TnC1XpZhnxVTWknPFDZmlkHwI5TS8jbGFRzDEcQAiHBREeB0vkF1ncuCc3xMZ5ITetMsT5Rx-AiAWvsiS2qTqcUa5yvKVNQYCazHA3VbLoqRPgEtBfbPEto1T3pFVDRJz6LuXvaDJvvZIp5hOPPqFYwo8dEdpqoCvcfkkbprbQ1PfH1rIwqP9_EAfCuEjtB-8g"
                    onError={(e) => {
                      e.currentTarget.src = '/calispec-logo-transparent.png';
                    }}
                  />
                </div>
              </div>
            </div>

            {/* Headline with Radiant Cyan Glow */}
            <h1 className="font-headline-xl text-2xl sm:text-3xl md:text-4xl text-white tracking-tight font-bold max-w-2xl text-center group-hover/center:scale-[1.01] transition-transform duration-300">
              How can we{' '}
              <span className="bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 via-sky-300 to-blue-400 drop-shadow-[0_0_25px_rgba(0,242,254,0.6)]">
                assist you
              </span>
              ?
            </h1>
          </section>

          {/* Active Conversation Messages Stream */}
          <section className="flex flex-col space-y-6 w-full max-w-3xl mt-2" id="chat-stream">
            {messages.map((message) => (
              <ChatMessage
                key={message.id}
                message={message}
                onInspect={(doc) => setInspectingDoc(doc)}
              />
            ))}
            {/* Dedicated scroll clearance spacer so last message is never covered by bottom input bar */}
            {messages.length > 0 && (
              <div className="h-16 w-full shrink-0 pointer-events-none" aria-hidden="true" />
            )}
          </section>
        </div>
      </main>

      {/* Floating Glassmorphic Glowing Prompt Bar (Proper Medium Size) */}
      <div className="fixed bottom-4 sm:bottom-6 inset-x-0 z-30 px-4 max-w-2xl mx-auto pointer-events-none">
        <div className="relative">
          <div className="absolute -inset-1 bg-gradient-to-r from-blue-600/35 via-cyan-400/40 to-blue-600/35 rounded-full blur-lg opacity-75 group-focus-within:opacity-100 transition-opacity duration-500 animate-pulse pointer-events-none"></div>
          <div className="pointer-events-auto relative rounded-full bg-slate-950/90 backdrop-blur-2xl border border-cyan-400/50 px-4 py-2 sm:px-5 sm:py-2.5 shadow-[0_0_22px_rgba(0,242,254,0.32),inset_0_1px_2px_rgba(255,255,255,0.3),inset_0_0_15px_rgba(0,242,254,0.15)] transition-all duration-300 focus-within:border-cyan-300 focus-within:shadow-[0_0_32px_rgba(0,242,254,0.55),inset_0_2px_4px_rgba(255,255,255,0.45)] flex items-center gap-2.5">
            <div className="flex-1 flex items-center min-w-0 pl-1">
              <input
                autoComplete="off"
                className="w-full bg-transparent border-none outline-none font-body-md text-sm sm:text-[15px] text-slate-100 placeholder:text-slate-500 focus:ring-0 focus:outline-none min-w-0 py-0.5"
                id="prompt-input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                placeholder={
                  isRecording
                    ? 'Listening to voice query...'
                    : 'Ask about companies, persons, locations, or uploaded datasets...'
                }
                type="text"
              />
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                className={`w-8 h-8 sm:w-9 sm:h-9 rounded-full border text-slate-300 hover:text-cyan-400 flex items-center justify-center transition-all ${
                  isRecording
                    ? 'bg-rose-500/20 border-rose-500 text-rose-400 animate-pulse'
                    : 'bg-slate-900/90 hover:bg-slate-800 border-slate-700/80 hover:border-cyan-500/50'
                }`}
                id="mic-btn"
                onClick={toggleDictation}
                title={isRecording ? 'Stop Voice Input' : 'Voice Input'}
                type="button"
              >
                <span className="material-symbols-outlined text-base sm:text-lg">mic</span>
              </button>
              <button
                className="w-8 h-8 sm:w-9 sm:h-9 rounded-full bg-gradient-to-tr from-cyan-500 to-sky-400 hover:from-cyan-400 hover:to-sky-300 text-slate-950 font-bold flex items-center justify-center shadow-[0_0_12px_rgba(0,242,254,0.55)] hover:shadow-[0_0_20px_rgba(0,242,254,0.85)] active:scale-95 transition-all disabled:opacity-50"
                id="send-btn"
                onClick={() => handleSendMessage()}
                disabled={loading}
                title="Send Prompt"
                type="button"
              >
                <span className="material-symbols-outlined text-base sm:text-lg">arrow_upward</span>
              </button>
            </div>
          </div>
        </div>
        <div className="text-center mt-1.5 px-4">
          <span className="font-label-sm text-[10px] text-slate-400/80 tracking-tight">
            CALISPEC provides automated technical telemetry. Verify primary standards with accredited metrology labs.
          </span>
        </div>
      </div>

      {/* File Upload Modal */}
      <FileUploadModal
        isOpen={uploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
        onUploadSuccess={handleUploadSuccess}
      />

      {/* Raw Document Inspector Modal */}
      {inspectingDoc && (
        <DocumentInspectorModal
          record={inspectingDoc}
          onClose={() => setInspectingDoc(null)}
        />
      )}
    </div>
  );
}
