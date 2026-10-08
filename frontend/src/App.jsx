import React, { useState, useEffect, useRef } from 'react';
import ChatMessage from './components/ChatMessage';
import Sidebar from './components/Sidebar';
import FileUploadModal from './components/FileUploadModal';
import DocumentInspectorModal from './components/DocumentInspectorModal';
import CalispecLogo from './components/CalispecLogo';
import LoginModal from './components/LoginModal';
import {
  sendChatMessage,
  fetchDatasets,
  deleteDatasetApi,
  getStoredUser,
  fetchCurrentUser,
  setAuthSession,
  logoutApi
} from './api';

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
  const [cleanModalOpen, setCleanModalOpen] = useState(false);
  const [docsDropdownOpen, setDocsDropdownOpen] = useState(false);
  const [docSearchQuery, setDocSearchQuery] = useState('');
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

  // Authenticated user state & profile dropdown
  const [currentUser, setCurrentUser] = useState(() => getStoredUser());
  const isDataUploader = currentUser?.role === 'DATA_UPLOADER';
  const isChatUser = currentUser?.role === 'CHAT_USER';

  const profilePanelRef = useRef(null);
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [loginError, setLoginError] = useState('');

  // Check auth and verify token validity on mount, handling Google OAuth redirect
  useEffect(() => {
    async function initAuth() {
      // Check if returning from Google OAuth redirect with ?token=...
      const params = new URLSearchParams(window.location.search);
      const token = params.get('token');
      const authError = params.get('auth_error');

      if (token) {
        const user_id = params.get('user_id') || '';
        const email = params.get('email') || '';
        const role = params.get('role') || 'CHAT_USER';
        const userObj = { user_id, email, role };

        setAuthSession(token, userObj);
        setCurrentUser(userObj);

        // Remove token query parameters from browser URL bar cleanly
        window.history.replaceState({}, document.title, window.location.pathname);

        // Fetch authoritative profile from backend /api/auth/me
        const freshUser = await fetchCurrentUser();
        if (freshUser) {
          setCurrentUser(freshUser);
        }
        return;
      }

      if (authError) {
        window.history.replaceState({}, document.title, window.location.pathname);
        let errorMsg = 'Google authentication could not be completed.';
        if (authError === 'google_oauth_not_configured') {
          errorMsg = 'Google OAuth credentials are not yet configured on the server. Please check backend/.env.';
        } else if (authError === 'cancelled' || authError === 'access_denied') {
          errorMsg = 'Google authentication was cancelled.';
        }
        setLoginError(errorMsg);
        setLoginModalOpen(true);
      }

      // Verify any existing stored token
      const user = await fetchCurrentUser();
      if (user) {
        setCurrentUser(user);
      } else {
        setCurrentUser(null);
      }
    }
    initAuth();
  }, []);

  const handleLoginSuccess = (user) => {
    setCurrentUser(user);
    setLoginModalOpen(false);
    setLoginError('');
    loadDatasets();
  };


  const handleLogout = async () => {
    await logoutApi();
    setCurrentUser(null);
    setUploadModalOpen(false);
  };

  // Fetch uploaded datasets on mount
  useEffect(() => {
    loadDatasets();
  }, [currentUser]);

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

  // Close dropdowns on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (docsPanelRef.current && !docsPanelRef.current.contains(e.target)) {
        setDocsDropdownOpen(false);
      }
      if (profilePanelRef.current && !profilePanelRef.current.contains(e.target)) {
        setProfileDropdownOpen(false);
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
    setDocsDropdownOpen(false);

    if (newDataset && (newDataset.filename || newDataset.count)) {
      const fileName = newDataset.filename || `${newDataset.count} uploaded datasets`;
      const recCount = newDataset.record_count?.toLocaleString() || newDataset.total_records?.toLocaleString() || 'All';
      const announcementMsg = {
        id: `assistant-dataset-ready-${Date.now()}`,
        role: 'assistant',
        is_system_notice: true,
        text: `Your dataset is ready for private AI search.\n\n📄 File: ${fileName}\n📊 Records: ${recCount}\n\nThis file is now part of the searchable pool. All queries search across all uploaded datasets by default!`,
        dataset_name: fileName,
      };

      setMessages((prev) => [...prev, announcementMsg]);
    }
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
        understood_as: response.understood_as,
        groups: response.groups,
        not_found: response.not_found,
        suggestions: response.suggestions,
        notes: response.notes,
        total: response.total,
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

  const activeDoc = datasets.find((d) => d.dataset_id === activeDatasetId);
  const isAll = !activeDatasetId || activeDatasetId === 'all' || activeDatasetId === 'default' || !activeDoc;

  // Alphabetical sorting of documents by filename
  const sortedDatasets = [...datasets].sort((a, b) =>
    (a.filename || '').localeCompare(b.filename || '', undefined, { sensitivity: 'base' })
  );

  // Search filtering by typed query
  const filteredDatasets = docSearchQuery.trim()
    ? sortedDatasets.filter((d) =>
        (d.filename || '').toLowerCase().includes(docSearchQuery.trim().toLowerCase())
      )
    : sortedDatasets;

  return (
    <div className="bg-[#f8fafc] text-slate-800 antialiased h-screen flex flex-col justify-between overflow-hidden selection:bg-sky-100 selection:text-sky-900 relative">
      {/* Background Layer: Tech Grid & Ambient AI Metrology Glow */}
      <div className="absolute inset-0 tech-grid-pattern pointer-events-none z-0"></div>
      <div className="absolute inset-0 ambient-glow pointer-events-none z-0"></div>
      <div className="absolute inset-0 calibration-rings pointer-events-none z-0"></div>

      {/* BEGIN: TopHeader */}
      <header className="relative z-40 w-full px-6 py-4 flex items-center justify-between border-b border-sky-100/70 bg-white/70 backdrop-blur-md shrink-0">
        {/* Left Navigation: Hamburger Menu & Authentic CALISPEC Logo */}
        <div className="flex items-center space-x-5">
          {/* Circular Hamburger Button */}
          <button
            aria-label="Open Navigation Menu"
            className="w-10 h-10 rounded-full flex items-center justify-center text-slate-600 bg-white border border-slate-200 hover:text-sky-600 hover:border-sky-200 hover:bg-sky-50/50 transition-all duration-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-500/20"
            data-purpose="toggle-sidebar"
            type="button"
            onClick={() => setSidebarOpen((prev) => !prev)}
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              viewBox="0 0 24 24"
            >
              <line x1="4" x2="20" y1="6" y2="6"></line>
              <line x1="4" x2="20" y1="12" y2="12"></line>
              <line x1="4" x2="20" y1="18" y2="18"></line>
            </svg>
          </button>

          {/* Authentic CALISPEC Logo */}
          <a
            className="flex items-center cursor-pointer select-none transition-transform hover:opacity-95"
            data-purpose="brand-logo"
            href="#"
            onClick={handleNewChat}
          >
            <img
              alt="CALISPEC - Proficient and Nimble"
              className="h-10 sm:h-11 md:h-12 w-auto object-contain select-none"
              src="/calispec-logo-transparent.png"
            />
          </a>
        </div>

        {/* Right Navigation: Uploaded Documents Indicator & User Profile */}
        <div className="flex items-center space-x-2.5">
          <div className="relative z-50" ref={docsPanelRef}>
            <div
              className={`flex items-center space-x-2.5 px-4 py-2 rounded-full border transition-all cursor-pointer shadow-sm group select-none ${
                activeDoc
                  ? 'border-sky-300 bg-sky-50/70 text-sky-900'
                  : 'border-sky-200/80 bg-white/90 text-slate-700 hover:border-sky-300'
              }`}
              data-purpose="documents-status-pill"
              onClick={() => setDocsDropdownOpen(!docsDropdownOpen)}
            >
              {/* Database Icon */}
              <svg
                className="w-4 h-4 text-sky-600 group-hover:scale-105 transition-transform"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                viewBox="0 0 24 24"
              >
                <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
                <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
                <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
              </svg>
              {/* Status Label */}
              <span className="text-sm font-medium tracking-tight truncate max-w-[170px]" title={activeDoc ? activeDoc.filename : 'Uploaded Documents'}>
                {activeDoc ? activeDoc.filename : 'Uploaded Documents'}
              </span>
              {/* Indexed / Active Badge */}
              <span className={`text-xs px-2.5 py-0.5 font-semibold rounded-full ${
                activeDoc
                  ? 'text-emerald-700 bg-emerald-100'
                  : 'text-sky-700 bg-sky-100'
              }`}>
                {activeDoc ? 'Filtered' : datasets.length > 0 ? `${datasets.length} Indexed` : 'All Files'}
              </span>
              {/* Dropdown Chevron */}
              <svg
                className={`w-3.5 h-3.5 text-slate-400 group-hover:text-slate-600 transition-transform duration-200 ml-0.5 ${
                  docsDropdownOpen ? 'rotate-180' : ''
                }`}
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2.5"
                viewBox="0 0 24 24"
              >
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
            </div>

            {/* Dropdown Menu */}
            {docsDropdownOpen && (
              <div
                className="absolute right-0 mt-2.5 w-96 rounded-2xl bg-white border border-slate-200 shadow-[0_12px_36px_rgba(15,23,42,0.12)] backdrop-blur-xl p-4 z-50 animate-fadeIn"
                id="db-docs-panel"
              >
                {/* Header */}
                <div className="flex items-center justify-between pb-2.5 mb-2.5 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-sky-600 text-base">folder_open</span>
                    <span className="text-xs font-bold text-slate-800 tracking-wide uppercase font-headline-xl">
                      Indexed Documents
                    </span>
                    <span className="text-[10px] text-slate-400 font-normal">({sortedDatasets.length})</span>
                  </div>
                  {activeDoc ? (
                    <button
                      type="button"
                      onClick={() => setActiveDatasetId('all')}
                      className="text-[10px] text-sky-600 hover:text-sky-800 bg-sky-50 hover:bg-sky-100 px-2 py-0.5 rounded border border-sky-200 font-semibold transition-all"
                      title="Clear selection and search all database files"
                    >
                      Search All Files
                    </button>
                  ) : (
                    <span className="text-[10px] font-label-sm text-sky-700 bg-sky-50 px-2 py-0.5 rounded border border-sky-200 font-semibold">
                      Searching All Files
                    </span>
                  )}
                </div>

                {/* Search by typing input box */}
                <div className="relative mb-2.5">
                  <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm pointer-events-none">
                    search
                  </span>
                  <input
                    type="text"
                    placeholder="Search documents by name..."
                    value={docSearchQuery}
                    onChange={(e) => setDocSearchQuery(e.target.value)}
                    className="w-full pl-8 pr-7 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500 transition-all"
                  />
                  {docSearchQuery && (
                    <button
                      type="button"
                      onClick={() => setDocSearchQuery('')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-0.5"
                      title="Clear search"
                    >
                      <span className="material-symbols-outlined text-xs">close</span>
                    </button>
                  )}
                </div>

                {/* Scope Hint */}
                <div className="mb-2 px-1 text-[11px] text-slate-500 flex items-center justify-between">
                  <span>
                    {activeDoc ? (
                      <>Active: <strong className="text-sky-700">{activeDoc.filename}</strong></>
                    ) : (
                      <>Active: <strong className="text-slate-700">All Files</strong> (No filter)</>
                    )}
                  </span>
                  <span className="text-[10px] text-slate-400">
                    {activeDoc ? 'Click active doc to deselect' : 'Click a doc to search it'}
                  </span>
                </div>

                {/* Document List (Alphabetical Order, Scrollable) */}
                <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
                  {filteredDatasets.length === 0 ? (
                    <div className="py-6 text-center text-xs text-slate-400">
                      {datasets.length === 0 ? (
                        <p>No documents uploaded yet.</p>
                      ) : (
                        <div>
                          <p>No documents matching &ldquo;{docSearchQuery}&rdquo;</p>
                          <button
                            type="button"
                            onClick={() => setDocSearchQuery('')}
                            className="mt-1 text-sky-600 hover:text-sky-700 underline font-medium"
                          >
                            Clear search
                          </button>
                        </div>
                      )}
                    </div>
                  ) : (
                    filteredDatasets.map((d) => {
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
                          ? 'text-rose-500'
                          : ext === 'json'
                          ? 'text-sky-600'
                          : ext === 'xml'
                          ? 'text-amber-600'
                          : 'text-emerald-600';

                      return (
                        <div
                          key={d.dataset_id}
                          className={`group flex items-center justify-between p-2 rounded-xl border transition-all cursor-pointer ${
                            isSelected
                              ? 'bg-sky-50/90 border-sky-400 ring-1 ring-sky-300 shadow-xs'
                              : 'bg-slate-50/70 hover:bg-sky-50/40 border-slate-200/80 hover:border-sky-300'
                          }`}
                          title={isSelected ? `Click to deselect and search all files` : `Click to search only ${d.filename}`}
                          onClick={() => {
                            if (isSelected) {
                              // Clicking active doc deselects it -> search all files
                              setActiveDatasetId('all');
                            } else {
                              // Clicking doc selects it -> search only this doc
                              setActiveDatasetId(d.dataset_id);
                            }
                          }}
                        >
                          <div className="flex items-center gap-2.5 truncate flex-1 min-w-0 pr-1">
                            <span className={`material-symbols-outlined ${iconColor} text-lg flex-shrink-0`}>
                              {icon}
                            </span>
                            <div className="truncate">
                              <p className="text-xs font-semibold text-slate-800 truncate" title={d.filename}>
                                {d.filename}
                              </p>
                              <p className="text-[10px] font-label-sm text-slate-500">
                                {d.record_count?.toLocaleString()} rows &bull; .{ext}
                              </p>
                            </div>
                          </div>

                          <div className="flex items-center gap-1.5 flex-shrink-0">
                            {isSelected && confirmDeleteId !== d.dataset_id && (
                              <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-50 border border-emerald-300 text-emerald-700 font-label-sm font-semibold">
                                Active
                              </span>
                            )}

                            {/* Delete Dataset Button (Restricted to DATA_UPLOADER) */}
                            {isDataUploader && (
                              confirmDeleteId === d.dataset_id ? (
                                <div className="flex items-center gap-1 animate-fadeIn">
                                  <button
                                    type="button"
                                    className="p-1 text-xs text-rose-600 hover:text-rose-700 bg-rose-50 rounded border border-rose-200 transition-all font-medium"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleDeleteDataset(d.dataset_id);
                                      setConfirmDeleteId(null);
                                    }}
                                  >
                                    Delete
                                  </button>
                                  <button
                                    type="button"
                                    className="p-1 text-xs text-slate-500 hover:text-slate-700 bg-slate-100 rounded transition-all"
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
                                  className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-rose-500 transition-all"
                                  title="Delete Dataset"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setConfirmDeleteId(d.dataset_id);
                                  }}
                                >
                                  <span className="material-symbols-outlined text-xs">delete</span>
                                </button>
                              )
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>

                {/* Upload Data File Button (Restricted to DATA_UPLOADER) */}
                {isDataUploader && (
                  <div className="mt-3 pt-2.5 border-t border-slate-100 flex flex-col gap-1.5">
                    <button
                      type="button"
                      className="w-full flex items-center justify-center gap-2 py-2 rounded-xl bg-sky-50 hover:bg-sky-100 text-xs font-semibold text-sky-700 border border-sky-200 transition-all shadow-xs"
                      onClick={() => {
                        setDocsDropdownOpen(false);
                        setUploadModalOpen(true);
                      }}
                    >
                      <span className="material-symbols-outlined text-sm">upload_file</span>
                      <span>Upload New Data File (.csv, .xlsx, .json, .xml, .txt)</span>
                    </button>
                  </div>
                )}
              </div>
            )}
        </div>

        {/* Round Profile Button & User Dropdown */}
        <div className="relative z-50" ref={profilePanelRef}>
          <button
            type="button"
            onClick={() => {
              if (currentUser) {
                setProfileDropdownOpen(!profileDropdownOpen);
              } else {
                setLoginModalOpen(true);
              }
            }}
            className="w-10 h-10 rounded-full flex items-center justify-center transition-all shadow-xs focus:outline-none select-none cursor-pointer"
            title={currentUser ? `Profile: ${currentUser.email}` : "Sign In as Uploader"}
          >
            {currentUser ? (
              <div className="relative w-10 h-10 rounded-full bg-gradient-to-tr from-sky-600 to-indigo-600 text-white font-bold text-sm flex items-center justify-center border-2 border-white shadow-sm ring-2 ring-sky-200 hover:ring-sky-400 transition-all">
                {currentUser.email ? currentUser.email.charAt(0).toUpperCase() : 'U'}
                {/* Active online dot */}
                <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-emerald-500 border-2 border-white rounded-full"></span>
              </div>
            ) : (
              <div className="w-10 h-10 rounded-full bg-slate-100 hover:bg-sky-50 border border-slate-300 hover:border-sky-300 text-slate-600 hover:text-sky-600 flex items-center justify-center transition-all shadow-2xs">
                <span className="material-symbols-outlined text-xl">person</span>
              </div>
            )}
          </button>

          {/* Profile Dropdown Menu (Only shown when user clicks their round profile) */}
          {currentUser && profileDropdownOpen && (
            <div
              className="absolute right-0 mt-2.5 w-64 rounded-2xl bg-white border border-slate-200 shadow-[0_12px_36px_rgba(15,23,42,0.15)] p-4 z-50 animate-fadeIn"
            >
              <div className="flex items-center gap-3 pb-3 border-b border-slate-100">
                <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-sky-600 to-indigo-600 text-white font-bold text-sm flex items-center justify-center shrink-0 shadow-sm">
                  {currentUser.email ? currentUser.email.charAt(0).toUpperCase() : 'U'}
                </div>
                <div className="truncate flex-1 min-w-0">
                  <p className="text-xs font-bold text-slate-800 truncate" title={currentUser.email}>
                    {currentUser.email}
                  </p>
                  <span
                    className={`inline-block text-[9px] font-bold px-2 py-0.5 mt-0.5 rounded-full uppercase tracking-wider ${
                      isDataUploader
                        ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                        : 'bg-sky-100 text-sky-800 border border-sky-300'
                    }`}
                  >
                    {isDataUploader ? 'DATA UPLOADER' : 'CHAT USER'}
                  </span>
                </div>
              </div>

              <div className="py-2.5 text-[11px] flex flex-col gap-2">
                {isDataUploader ? (
                  <>
                    <span className="flex items-center gap-1.5 text-emerald-700 font-medium">
                      <span className="material-symbols-outlined text-xs">verified</span>
                      <span>Upload &amp; dataset management active</span>
                    </span>
                  </>
                ) : (
                  <span className="flex items-center gap-1.5 text-slate-500">
                    <span className="material-symbols-outlined text-xs">search</span>
                    <span>Chat &amp; search access active</span>
                  </span>
                )}
              </div>

              {/* Sign Out Button INSIDE the profile dropdown */}
              <div className="pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => {
                    setProfileDropdownOpen(false);
                    handleLogout();
                  }}
                  className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-slate-50 hover:bg-rose-50 text-slate-700 hover:text-rose-600 border border-slate-200 hover:border-rose-200 text-xs font-semibold transition-all cursor-pointer"
                >
                  <span className="material-symbols-outlined text-sm">logout</span>
                  <span>Sign Out</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
      </header>
      {/* END: TopHeader */}

      {/* BEGIN: Side-by-Side Workspace Layout */}
      <div className="flex-1 flex overflow-hidden relative z-10 w-full min-h-0">
        {/* Left Sidebar Menu (Visible when toggled, docked alongside chat) */}
        {sidebarOpen && (
          <Sidebar
            onClose={() => setSidebarOpen(false)}
            onNewChat={handleNewChat}
            chatHistory={chatHistory}
            currentChatId={currentChatId}
            onSelectChat={handleSelectChat}
            onDeleteChat={handleDeleteChat}
            onClearHistory={handleClearHistory}
          />
        )}

        {/* Right Chat Column (Fully visible alongside menu, never hidden in background) */}
        <div className="flex-1 flex flex-col min-w-0 h-full justify-between relative overflow-hidden">
          {/* BEGIN: MainContentArea */}
          <main
            className={`relative z-10 flex-1 flex flex-col items-center px-4 max-w-4xl mx-auto select-none w-full overflow-hidden ${
              messages.length === 0 ? 'justify-center -mt-10' : 'justify-start pt-2'
            }`}
          >

            <div className="flex flex-col w-full h-full justify-between pb-2">
              {messages.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center space-y-4 px-4 my-auto">
                  {/* Main Heading with High-Precision Accent */}
                  <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-slate-900 leading-tight">
                    Search Your <span className="text-[#0284c7] drop-shadow-sm">Business Data</span>
                  </h1>
                  {/* Subtitle */}
                  <p className="text-base sm:text-lg md:text-xl text-slate-500 max-w-2xl mx-auto font-normal leading-relaxed">
                    Ask questions about companies, people, contacts, locations, departments, and more.
                  </p>
                </div>
              ) : (
                /* Conversation Scroll Stage */
                <div
                  className="w-full flex-1 overflow-y-auto space-y-6 pt-4 pb-6 px-1 md:px-3"
                  id="main-scroll-view"
                  ref={scrollViewRef}
                >
                  {messages.map((message) => (
                    <ChatMessage
                      key={message.id}
                      message={message}
                      onInspect={(doc) => setInspectingDoc(doc)}
                      onRunSearch={(searchQuery) => handleSendMessage(searchQuery)}
                    />
                  ))}
                </div>
              )}
            </div>
          </main>
          {/* END: MainContentArea */}

          {/* BEGIN: FloatingSearchInputArea */}
          <footer className="relative z-20 w-full pb-8 sm:pb-10 px-4 sm:px-6 flex justify-center shrink-0">
            <div className="w-full max-w-3xl">
              {/* Glow Search Container */}
              <div
                className="glow-search-bar bg-white rounded-full flex items-center px-3.5 py-2.5 sm:px-4 sm:py-3"
                data-purpose="search-box-container"
              >
                {/* Upload / Add Document Circular Button (Restricted to DATA_UPLOADER) */}
                {isDataUploader && (
                  <button
                    aria-label="Attach documents or add files"
                    className="w-9 h-9 rounded-full flex items-center justify-center text-slate-500 hover:text-sky-600 hover:bg-sky-50 active:scale-95 transition-all duration-150 focus:outline-none"
                    data-purpose="attachment-button"
                    type="button"
                    onClick={() => setUploadModalOpen(true)}
                  >
                    <svg className="w-5 h-5 stroke-[2.2]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <line x1="12" x2="12" y1="5" y2="19"></line>
                      <line x1="5" x2="19" y1="12" y2="12"></line>
                    </svg>
                  </button>
                )}

                {/* Text Input Field */}
                <input
                  className="flex-1 bg-transparent border-none text-slate-800 placeholder-slate-400 text-base sm:text-lg px-3 focus:outline-none focus:ring-0"
                  data-purpose="query-input"
                  placeholder="Type here..."
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      handleSendMessage();
                    }
                  }}
                />

                {/* Right Side Controls: Microphone & Active Send Arrow */}
                <div className="flex items-center space-x-1 sm:space-x-2">
                  {/* Voice Input Button */}
                  <button
                    aria-label="Voice input"
                    className={`w-9 h-9 rounded-full flex items-center justify-center transition-all focus:outline-none ${
                      isRecording
                        ? 'bg-rose-100 text-rose-600 animate-pulse'
                        : 'text-slate-400 hover:text-sky-600 hover:bg-sky-50'
                    }`}
                    data-purpose="voice-input-button"
                    type="button"
                    onClick={toggleDictation}
                    title={isRecording ? 'Stop Voice Input' : 'Voice Input'}
                  >
                    <svg className="w-5 h-5 stroke-[2]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" strokeLinecap="round" strokeLinejoin="round"></path>
                      <path d="M19 10v2a7 7 0 01-14 0v-2" strokeLinecap="round" strokeLinejoin="round"></path>
                      <line x1="12" x2="12" y1="19" y2="23"></line>
                      <line x1="8" x2="16" y1="23" y2="23"></line>
                    </svg>
                  </button>

                  {/* Vibrant Precision Blue Send Button */}
                  <button
                    aria-label="Send query"
                    className="w-10 h-10 rounded-full bg-[#0284c7] hover:bg-[#0369a1] text-white flex items-center justify-center shadow-md shadow-sky-500/25 active:scale-95 transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-sky-500/50 disabled:opacity-50"
                    data-purpose="submit-search-button"
                    type="button"
                    disabled={loading}
                    onClick={() => handleSendMessage()}
                    title="Send query"
                  >
                    <svg className="w-5 h-5 stroke-[2.5]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <line x1="12" x2="12" y1="19" y2="5"></line>
                      <polyline points="5 12 12 5 19 12"></polyline>
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </footer>
          {/* END: FloatingSearchInputArea */}
        </div>
      </div>
      {/* END: Side-by-Side Workspace Layout */}

      {/* Enterprise Authentication Login Modal (Only when opened by user) */}
      <LoginModal
        isOpen={loginModalOpen}
        onClose={() => {
          setLoginModalOpen(false);
          setLoginError('');
        }}
        onLoginSuccess={handleLoginSuccess}
        initialError={loginError}
      />


      {/* File Upload Modal (Only for DATA_UPLOADER) */}
      <FileUploadModal
        isOpen={uploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
        onUploadSuccess={handleUploadSuccess}
      />


      {/* Document Raw JSON Inspector Modal */}
      <DocumentInspectorModal
        record={inspectingDoc}
        onClose={() => setInspectingDoc(null)}
      />
    </div>
  );
}
