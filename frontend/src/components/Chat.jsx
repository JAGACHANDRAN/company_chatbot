import React, { useRef, useEffect } from 'react';
import ChatMessage from './ChatMessage';
import EmptyState from './EmptyState';

export default function Chat({
  messages,
  onSelectPrompt,
  onOpenUploadModal,
  loading,
  onInspect,
  activeDatasetName,
  activeDatasetFields,
}) {
  const bottomRef = useRef(null);

  useEffect(() => {
    // Smooth auto scroll to latest message
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  if (messages.length === 0) {
    return (
      <EmptyState
        onSelectPrompt={onSelectPrompt}
        onOpenUploadModal={onOpenUploadModal}
        activeDatasetName={activeDatasetName}
        activeDatasetFields={activeDatasetFields}
      />
    );
  }

  return (
    <div className="chat-stream">
      {messages.map((msg, index) => (
        <ChatMessage key={msg.id || index} message={msg} onInspect={onInspect} />
      ))}
      <div ref={bottomRef} style={{ height: '10px' }} />
    </div>
  );
}
