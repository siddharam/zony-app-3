import React, { useState, useEffect, useRef } from 'react';
import { io } from 'socket.io-client';
import { MessageSquare, Send, AlertTriangle, FileText, X, Loader2 } from 'lucide-react';

// --- Configuration ---
const BACKEND_URL = 'http://localhost:5001';
const socket = io(BACKEND_URL);

// --- Helper Components ---

const LoadingSpinner = ({ text = "Loading..." }) => (
    <div className="flex flex-col justify-center items-center h-full text-slate-500">
        <Loader2 className="animate-spin h-8 w-8 mb-2" />
        <p className="font-semibold text-sm">{text}</p>
    </div>
);

const ErrorDisplay = ({ message }) => (
    <div className="text-center text-red-600 mt-10 bg-red-50 p-4 rounded-xl shadow-md border border-red-200">
        <div className="flex justify-center mb-2">
            <AlertTriangle className="w-7 h-7 text-red-500" />
        </div>
        <p className="font-bold text-md">An Error Occurred</p>
        <p className="text-xs mt-1">{message}</p>
    </div>
);

// --- NEW: Reusable Badge with Tooltip Component ---
const BadgeWithTooltip = ({ text }) => {
    return (
        <div className="relative group flex items-center">
            <span className="truncate max-w-[120px] inline-block bg-slate-100 text-slate-700 text-xs font-medium px-2 py-1 rounded-full border border-slate-200 cursor-default">
                {text}
            </span>
            {/* Tooltip: appears on hover */}
            <div className="absolute left-0 bottom-full mb-2 w-max max-w-xs bg-slate-800 text-white text-xs rounded-md py-1.5 px-3 opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none shadow-lg z-10">
                {text}
                <svg className="absolute text-slate-800 h-2 w-full left-0 top-full" x="0px" y="0px" viewBox="0 0 255 255" xmlSpace="preserve">
                    <polygon className="fill-current" points="0,0 127.5,127.5 255,0"/>
                </svg>
            </div>
        </div>
    );
};


const UserMessage = ({ text }) => (
    <div className="flex justify-end mb-3">
        <div className="bg-indigo-600 text-white p-3 rounded-xl rounded-br-none max-w-sm md:max-w-md shadow-sm">
            <p className="text-sm">{text}</p>
        </div>
    </div>
);

const AiMessage = ({ text, isTyping }) => (
    <div className="flex gap-2 mb-3">
        <div className="w-7 h-7 rounded-full bg-indigo-500 text-white flex items-center justify-center font-bold text-xs shrink-0 shadow-sm">AI</div>
        <div className="bg-slate-100 p-3 rounded-xl rounded-tl-none max-w-sm md:max-w-md shadow-sm">
            {isTyping ? (
                <div className="flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 bg-slate-400 rounded-full animate-bounce delay-75"></span>
                    <span className="h-1.5 w-1.5 bg-slate-400 rounded-full animate-bounce delay-150"></span>
                    <span className="h-1.5 w-1.5 bg-slate-400 rounded-full animate-bounce delay-200"></span>
                </div>
            ) : (
                <p className="text-sm">{text}</p>
            )}
        </div>
    </div>
);

// --- MODIFIED: IntentCard now uses BadgeWithTooltip ---
const IntentCard = ({ intentData, isHighlighted, onClick }) => {
    if (!intentData || !intentData.intent) return null;

    const { displayName, description, filledSlots } = intentData.intent;
    const formatSlotName = (name) => {
        const result = name.replace(/([A-Z])/g, ' $1');
        return result.charAt(0).toUpperCase() + result.slice(1);
    };

    const highlightClass = isHighlighted ? 'transition-all duration-1000 bg-yellow-100' : 'bg-white';
    const cursorClass = onClick ? 'cursor-pointer hover:shadow-lg hover:border-indigo-300' : '';

    return (
        <div className={`p-3 rounded-xl shadow-md border border-slate-200 transition-all duration-200 ${highlightClass} ${cursorClass}`} onClick={onClick}>
            <div className="flex justify-between items-start">
                <div>
                    <span className="inline-block bg-blue-100 text-blue-800 text-xs font-semibold px-2 py-0.5 rounded-full mb-1.5">{displayName || "New Intent"}</span>
                    <h3 className="text-md font-bold text-slate-800">{description || "No description provided."}</h3>
                    <p className="text-xs text-slate-500 mt-1">Posted by: {intentData.userId}</p>
                </div>
            </div>
            {filledSlots && Object.keys(filledSlots).length > 0 && (
                <div className="mt-3 border-t border-slate-200 pt-3">
                    <h4 className="font-semibold text-xs mb-2 text-slate-600">Details</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-2 text-xs">
                        {Object.entries(filledSlots).map(([key, value]) => (
                             <div key={key} className="flex items-center justify-between">
                                <span className="text-slate-500 truncate pr-2">{formatSlotName(key)}:</span>
                                <BadgeWithTooltip text={String(value)} />
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};


const ChatListItem = ({ intentData, isSelected, onClick }) => {
    if (!intentData || !intentData.intent) return null;

    const { description } = intentData.intent;
    const slotPreview = Object.entries(intentData.intent.filledSlots || {})
        .map(([, value]) => `${String(value).slice(0, 15)}`)
        .join(', ');

    const selectedClass = isSelected ? 'bg-indigo-50' : 'hover:bg-slate-50';

    return (
        <div
            className={`flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors duration-150 ${selectedClass}`}
            onClick={onClick}
        >
            <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-full bg-slate-200 flex items-center justify-center">
                    <FileText className="w-5 h-5 text-slate-500" />
                </div>
            </div>
            <div className="flex-grow overflow-hidden">
                <div className="flex justify-between items-center">
                    <h4 className="font-bold text-sm text-slate-800 truncate">
                        {description || "Completed Intent"}
                    </h4>
                </div>
                <p className="text-xs text-slate-500 truncate">
                    {slotPreview || "No details captured."}
                </p>
            </div>
        </div>
    );
};


const ChatSheet = ({
    isOpen,
    onClose,
    thread,
    message,
    setMessage,
    isTyping,
    handleSendMessage,
    messagesEndRef
}) => {
    if (!isOpen) return null;

    return (
        <div className="absolute inset-0 z-20 flex flex-col justify-end">
            <div className="absolute inset-0 bg-black bg-opacity-40 animate-fade-in" onClick={onClose}></div>
            <div className="relative bg-white w-full h-[95%] rounded-t-2xl shadow-2xl flex flex-col animate-slide-up">
                <div className="p-3 border-b border-slate-200 flex justify-between items-center shrink-0">
                    <div className="font-bold text-md text-slate-700 flex-1 ml-2">New Conversation</div>
                    <button onClick={onClose} className="p-2 rounded-full hover:bg-slate-100">
                        <X className="w-5 h-5" />
                    </button>
                </div>
                <div className="flex-1 p-3 custom-scrollbar overflow-y-auto">
                    {thread && (
                        <>
                            {thread.messages.map((msg, index) =>
                                msg.role === 'user'
                                    ? <UserMessage key={index} text={msg.content} />
                                    : <AiMessage key={index} text={msg.content} />
                            )}
                            {isTyping && <AiMessage isTyping={true} />}
                            <div ref={messagesEndRef} />
                        </>
                    )}
                </div>
                <div className="p-3 border-t border-slate-200 shrink-0">
                    <form onSubmit={handleSendMessage} className="relative">
                        <input
                            value={message}
                            onChange={(e) => setMessage(e.target.value)}
                            type="text"
                            placeholder="Type your message..."
                            className="w-full bg-slate-100 border border-slate-200 rounded-lg py-2.5 pl-3 pr-10 focus:ring-2 focus:ring-indigo-500 outline-none text-sm"
                            autoFocus
                        />
                        <button type="submit" className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1.5 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:bg-indigo-300" disabled={isTyping || !message.trim()}>
                            <Send className="w-4 h-4" />
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
};


// --- Main App Component ---

export default function App() {
    // Authentication & Connection State
    const [username, setUsername] = useState('');
    const [isLoggedIn, setIsLoggedIn] = useState(false);
    const [isConnected, setIsConnected] = useState(socket.connected);

    // Chat Widget State
    const [isChatSheetOpen, setIsChatSheetOpen] = useState(false);
    const [thread, setThread] = useState(null);
    const [message, setMessage] = useState('');
    const [isTyping, setIsTyping] = useState(false);

    // Data State
    const [communityIntents, setCommunityIntents] = useState([]);
    const [userIntents, setUserIntents] = useState([]);
    const [selectedIntent, setSelectedIntent] = useState(null);
    const [isLoadingCommunityIntents, setIsLoadingCommunityIntents] = useState(true);
    const [isLoadingUserIntents, setIsLoadingUserIntents] = useState(false);
    const [fetchError, setFetchError] = useState(null);

    const messagesEndRef = useRef(null);

    // --- Effects ---

    useEffect(() => {
        function onConnect() { setIsConnected(true); }
        function onDisconnect() { setIsConnected(false); }
        socket.on('connect', onConnect);
        socket.on('disconnect', onDisconnect);

        const fetchCommunityIntents = async () => {
            setFetchError(null);
            setIsLoadingCommunityIntents(true);
            try {
                const response = await fetch(`${BACKEND_URL}/intents`);
                if (!response.ok) throw new Error(`Network response was not ok (${response.status})`);
                const data = await response.json();
                setCommunityIntents(data.map(intent => ({...intent, isNew: false })));
            } catch (error) {
                console.error("Failed to fetch community intents:", error);
                setFetchError('Could not connect to the server to load community intents.');
            } finally {
                setIsLoadingCommunityIntents(false);
            }
        };
        fetchCommunityIntents();

        socket.on('new_intent', (newIntent) => {
            setCommunityIntents(prev => [{ ...newIntent, isNew: true }, ...prev]);
            if (newIntent.userId === username) {
                setUserIntents(prev => [newIntent, ...prev]);
            }
        });

        return () => {
            socket.off('connect', onConnect);
            socket.off('disconnect', onDisconnect);
            socket.off('new_intent');
        };
    }, [username]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [thread]);

    useEffect(() => {
        const timers = communityIntents.map((intent, index) => {
            if (intent.isNew) {
                return setTimeout(() => {
                    setCommunityIntents(prev => {
                        const newIntents = [...prev];
                        if (newIntents[index]) newIntents[index].isNew = false;
                        return newIntents;
                    });
                }, 2500);
            }
            return null;
        });
        return () => timers.forEach(timer => clearTimeout(timer));
    }, [communityIntents]);


    // --- Handlers ---

    const handleLogin = async (e) => {
        e.preventDefault();
        if (username.trim()) {
            setIsLoggedIn(true);
            await fetchUserIntents(username.trim());
        }
    };

    const fetchUserIntents = async (user) => {
        setIsLoadingUserIntents(true);
        try {
            const response = await fetch(`${BACKEND_URL}/intents/${user}`);
            if (!response.ok) throw new Error('Failed to fetch user intents.');
            const data = await response.json();
            setUserIntents(data);
        } catch (error) {
            console.error(error);
        } finally {
            setIsLoadingUserIntents(false);
        }
    };

    const handleNewChat = () => {
        const newThreadId = `thread_${Date.now()}`;
        setThread({
            id: newThreadId,
            messages: [{ role: 'model', content: `Hi ${username}! I'm your AI assistant. How can I help you today?` }]
        });
        setIsChatSheetOpen(true);
    };
    
    const handleCloseChatSheet = () => {
        setIsChatSheetOpen(false);
        setThread(null);
    };

    const handleSendMessage = async (e) => {
        e.preventDefault();
        if (!message.trim() || !thread) return;

        const userMessage = { role: 'user', content: message };
        setThread(prev => ({ ...prev, messages: [...prev.messages, userMessage] }));

        const messageToSend = message;
        setMessage('');
        setIsTyping(true);

        try {
            const response = await fetch(`${BACKEND_URL}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId: username, threadId: thread.id, message: messageToSend })
            });

            if (!response.ok) throw new Error(`Network error: ${response.status}`);
            const data = await response.json();
            const aiMessage = { role: 'model', content: data.reply };

            setThread(prev => ({ ...prev, messages: [...prev.messages, aiMessage] }));

            if(data.reply.includes("I've posted your request")) {
                await fetchUserIntents(username);
                 setTimeout(() => {
                    handleCloseChatSheet();
                 }, 2000);
            }
        } catch (error) {
            console.error("Chat error:", error);
            const errorMessage = { role: 'model', content: `Sorry, I'm having trouble connecting. Please try again. (${error.message})` };
            setThread(prev => ({ ...prev, messages: [...prev.messages, errorMessage] }));
        } finally {
            setIsTyping(false);
        }
    };
    
    const handleIntentSelect = (intent) => {
        setSelectedIntent(intent);
    };

    // --- Render Logic ---

    if (!isLoggedIn) {
        return (
            <div className="bg-slate-100 h-screen w-screen flex items-center justify-center p-4">
                <div className="w-full max-w-sm mx-auto">
                    <form onSubmit={handleLogin} className="bg-white p-8 rounded-2xl shadow-lg text-center">
                        <h1 className="text-2xl font-bold text-slate-700 mb-2">Welcome Back</h1>
                        <p className="text-slate-500 mb-6">Enter your username to begin.</p>
                        <input
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            type="text"
                            placeholder="e.g., alex_123"
                            className="w-full px-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition duration-200"
                        />
                        <button type="submit" className="w-full bg-indigo-600 text-white font-semibold py-3 px-4 rounded-lg mt-4 hover:bg-indigo-700 active:scale-95 transition-all duration-200 shadow-md hover:shadow-lg">
                            Login
                        </button>
                    </form>
                </div>
            </div>
        );
    }

    return (
        <div className="h-screen w-screen bg-slate-100 text-slate-800 flex flex-col p-2">
            <header className="p-3 bg-white rounded-xl shadow-lg m-2 text-center shrink-0">
                 <h1 className="font-bold text-xl text-slate-800">Intent Management Dashboard</h1>
                 <p className="text-xs text-slate-500 mt-1">Welcome, {username}!</p>
            </header>

            <div className="flex-grow flex gap-4 p-2 overflow-hidden">
                {/* Left Panel (Chat Threads) */}
                <div className="w-4/12 flex flex-col">
                    <div className="p-3 bg-white rounded-xl shadow-lg flex-grow flex flex-col min-h-0 relative">
                        <div className="shrink-0 mb-3 text-center border-b border-slate-200 pb-3">
                           <h2 className="font-bold text-lg text-slate-800">Conversations</h2>
                        </div>
                        
                        <div className="overflow-y-auto flex-grow space-y-1 pr-1 custom-scrollbar">
                            {isLoadingUserIntents ? (
                                <LoadingSpinner text="Loading your chats..." />
                            ) : userIntents.length > 0 ? (
                                userIntents.map(intent => (
                                    <ChatListItem
                                        key={intent.intentId}
                                        intentData={intent}
                                        isSelected={selectedIntent?.intentId === intent.intentId}
                                        onClick={() => handleIntentSelect(intent)}
                                    />
                                ))
                            ) : (
                                <div className="text-center text-slate-400 mt-10 p-4">
                                    <MessageSquare className="w-10 h-10 mx-auto mb-2 text-slate-300" />
                                    <p className="font-semibold text-sm">No conversations yet.</p>
                                    <p className="text-xs">Start a new chat to begin.</p>
                                </div>
                            )}
                        </div>

                        <div className="shrink-0 pt-3 mt-2 border-t border-slate-200">
                             <button onClick={handleNewChat} className="w-full bg-indigo-600 text-white font-semibold py-2.5 px-4 rounded-lg hover:bg-indigo-700 active:scale-95 transition-all duration-200 shadow hover:shadow-md">
                                 + Start New Chat
                             </button>
                        </div>
                        
                        <ChatSheet
                            isOpen={isChatSheetOpen}
                            onClose={handleCloseChatSheet}
                            thread={thread}
                            message={message}
                            setMessage={setMessage}
                            isTyping={isTyping}
                            handleSendMessage={handleSendMessage}
                            messagesEndRef={messagesEndRef}
                        />
                    </div>
                </div>

                {/* Middle Panel: Selected Intent Details */}
                <div className="w-5/12 flex flex-col">
                    <div className="p-3 bg-white rounded-xl shadow-lg flex-grow flex flex-col min-h-0">
                         <h2 className="font-bold text-lg text-slate-800 mb-3 text-center shrink-0">Selected Intent Details</h2>
                        <div className="overflow-y-auto flex-grow pr-1">
                            {selectedIntent ? (
                                 <IntentCard intentData={selectedIntent} />
                            ) : (
                                 <div className="text-center text-slate-400 mt-16 flex flex-col items-center h-full justify-center">
                                     <FileText className="w-12 h-12 text-slate-300 mb-3" />
                                     <p className="font-semibold text-md">No Intent Selected</p>
                                     <p className="text-xs">Select a conversation on the left to see its details.</p>
                                 </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Right Panel: Community Intents */}
                <div className="w-3/12 flex flex-col">
                    <div className="p-3 bg-white rounded-xl shadow-lg flex-grow flex flex-col min-h-0">
                        <h2 className="font-bold text-lg text-slate-800 mb-3 text-center shrink-0">Community Feed</h2>
                        <div className="overflow-y-auto flex-grow space-y-2 pr-1">
                            {fetchError ? (
                                <ErrorDisplay message={fetchError} />
                            ) : isLoadingCommunityIntents ? (
                                <LoadingSpinner text="Loading..." />
                            ) : communityIntents.length > 0 ? (
                                communityIntents.map(intent => <IntentCard key={intent.intentId || intent.threadId} intentData={intent} isHighlighted={intent.isNew} />)
                            ) : (
                               <div className="text-center text-slate-400 mt-16 flex flex-col items-center">
                                   <FileText className="w-10 h-10 text-slate-300 mb-2" />
                                   <p className="font-semibold text-sm">Feed is empty.</p>
                                   <p className="text-xs">Be the first to post!</p>
                               </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}