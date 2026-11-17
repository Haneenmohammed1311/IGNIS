import {Children,cloneElement,isValidElement,lazy,Suspense,useEffect,useRef,useState,type ReactNode} from 'react';
import {Bot,ChevronDown,Grip,Maximize2,MessageCircle,Minimize2,Minus,Send,Trash2,X} from 'lucide-react';
import {request,type Filters} from './api';

const MarkdownAnswer=lazy(async()=>{
  const [markdown,gfm]=await Promise.all([import('react-markdown'),import('remark-gfm')]);
  function emphasizeNumbers(children:ReactNode):ReactNode{
    return Children.map(children,child=>{
      if(typeof child==='string')return child.split(/(\b\d[\d,]*(?:\.\d+)?%?)/g).map((part,index)=>
        /^\d/.test(part)?<span className="ai-chat-numeric" key={index}>{part}</span>:part);
      if(isValidElement<{children?:ReactNode}>(child))return cloneElement(child,{children:emphasizeNumbers(child.props.children)});
      return child;
    });
  }
  return {default:({content}:{content:string})=>{
    const highlighted=content.replace(/\[((?:nasa_firms_knowledge|AU|BR|ID|ZA)[^\]]+)\]/g,'`[$1]`');
    return <markdown.default remarkPlugins={[gfm.default]} components={{
      p:({children})=><p>{emphasizeNumbers(children)}</p>,
      li:({children})=><li>{emphasizeNumbers(children)}</li>,
      th:({children})=><th>{emphasizeNumbers(children)}</th>,
      td:({children})=><td>{emphasizeNumbers(children)}</td>,
      h1:({children})=><h1>{emphasizeNumbers(children)}</h1>,
      h2:({children})=><h2>{emphasizeNumbers(children)}</h2>,
      h3:({children})=><h3>{emphasizeNumbers(children)}</h3>,
      code:({children})=><code>{children}</code>,
    }}>{highlighted}</markdown.default>;
  }};
});

type CitationData = Record<string,unknown>;
type ChatReply = {
  answer:string;
  analytical_citations:string[];
  knowledge_citations:string[];
  suggested_questions:string[];
  analytical_facts:Record<string,CitationData>;
  knowledge_chunks:{id:string;title:string;text:string}[];
  scope_notes:string[];
};
type Message = {role:'user'|'assistant';content:string;reply?:ChatReply;error?:boolean};
type Size = {width:number;height:number};

const starters=[
  {label:'--compare-countries',question:'Compare total thermal detections between Brazil and Australia in 2020.'},
  {label:'--sensor-trend',question:'Which year had the highest MODIS mean FRP in Indonesia?'},
  {label:'--nasa-transition',question:'Why did Suomi NPP cease in November 2026, and how do I migrate VNP files to NOAA-20 and NOAA-21?'},
  {label:'--sensor-overpass-gap',question:'What is the difference between MODIS and VIIRS swath width and coverage gaps at the equator?'},
  {label:'--data-coverage',question:'In the currently selected country and year, why do VIIRS and MODIS detection counts differ?'},
];

export default function AiChat({filters}:{filters:Filters}){
  const [open,setOpen]=useState(false);
  const [expanded,setExpanded]=useState(false);
  const [size,setSize]=useState<Size>({width:380,height:520});
  const [messages,setMessages]=useState<Message[]>([]);
  const [draft,setDraft]=useState('');
  const [pending,setPending]=useState(false);
  const [error,setError]=useState('');
  const bottom=useRef<HTMLDivElement>(null);
  const resizeStart=useRef<{x:number;y:number;width:number;height:number}|null>(null);

  useEffect(()=>{bottom.current?.scrollIntoView({block:'end',behavior:'smooth'});},[messages,pending]);
  useEffect(()=>{
    if(!open)return;
    const close=(event:KeyboardEvent)=>{if(event.key==='Escape')setOpen(false);};
    window.addEventListener('keydown',close);
    return ()=>window.removeEventListener('keydown',close);
  },[open]);

  const send=async(question:string)=>{
    const text=question.trim();
    if(!text||pending)return;
    const prior=messages.slice(-12).map(({role,content})=>({role,content:content.slice(-1800)}));
    setMessages(current=>[...current,{role:'user',content:text}]);
    setDraft('');setError('');setPending(true);
    try{
      const controller=new AbortController();
      const reply=await request<ChatReply>('/chat',controller.signal,{
        message:text,history:prior,current_filters:filters,
      });
      setMessages(current=>[...current,{role:'assistant',content:reply.answer,reply}]);
    }catch(cause){
      const message=cause instanceof Error?cause.message:'Chat request failed.';
      setError(message);
      setMessages(current=>[...current,{role:'assistant',content:message,error:true}]);
    }finally{setPending(false);}
  };

  const resize=(event:React.PointerEvent<HTMLButtonElement>)=>{
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeStart.current={x:event.clientX,y:event.clientY,width:size.width,height:size.height};
  };
  const resizeMove=(event:React.PointerEvent<HTMLButtonElement>)=>{
    const start=resizeStart.current;
    if(!start)return;
    setExpanded(false);
    const minWidth=Math.min(320,window.innerWidth-24);
    const minHeight=Math.min(400,window.innerHeight-24);
    setSize({
      width:Math.max(minWidth,Math.min(window.innerWidth*.85,start.width+start.x-event.clientX)),
      height:Math.max(minHeight,Math.min(window.innerHeight*.88,start.height+start.y-event.clientY)),
    });
  };

  const clear=()=>{setMessages([]);setError('');setDraft('');};
  const windowSize={
    '--chat-width':`${size.width}px`,
    '--chat-height':`${size.height}px`,
  } as React.CSSProperties;

  return <div className="ai-chat-root">
    {!open&&<button className="ai-chat-launcher" aria-label="Open AI Assistant" title="Open AI Assistant" onClick={()=>setOpen(true)}>
      <MessageCircle size={23}/><span className="ai-chat-spark"><Bot size={12}/></span>
    </button>}
    {open&&<section className={'ai-chat-window'+(expanded?' expanded':'')} style={windowSize} aria-label="AI Assistant chat">
      <button className="ai-chat-resize" aria-label="Resize chat window" title="Drag to resize"
        onPointerDown={resize} onPointerMove={resizeMove}
        onPointerUp={()=>{resizeStart.current=null;}} onPointerCancel={()=>{resizeStart.current=null;}}>
        <Grip size={15}/>
      </button>
      <header className="ai-chat-header">
        <div className="ai-chat-title"><span><Bot size={17}/></span><div><strong>Intelligence Assistant</strong><small>IGNIS evidence dossier</small></div></div>
        <div className="ai-chat-actions">
          <button aria-label="Clear Chat" title="Clear Chat" onClick={clear}><Trash2 size={15}/></button>
          <button aria-label={expanded?'Shrink chat':'Expand chat'} title={expanded?'Shrink chat':'Expand chat'}
            onClick={()=>{setExpanded(!expanded);setSize({width:380,height:520});}}>
            {expanded?<Minimize2 size={15}/>:<Maximize2 size={15}/>}</button>
          <button aria-label="Minimize chat" title="Minimize to corner" onClick={()=>setOpen(false)}><Minus size={16}/><ChevronDown className="ai-chat-down" size={11}/></button>
        </div>
      </header>
      <div className="ai-chat-context">
        {filters.country} / {filters.year} · {filters.sensor??'All sensors'} · {filters.region?'Selected region':filters.polygon?'Custom area':'Entire country'}
      </div>
      <div className="ai-chat-messages" aria-live="polite">
        {!messages.length?<div className="ai-chat-starters">
          <div className="ai-chat-welcome"><span>IGNIS / ASSISTANT</span><h2>What would you like to explore?</h2>
            <p>Answers cite local release summaries and NASA FIRMS documentation.</p></div>
          {starters.map(item=><div className="ai-chat-starter-group" key={item.label}>
            <small>{item.label}</small><button disabled={pending} onClick={()=>void send(item.question)}>{item.question}</button>
          </div>)}
        </div>:messages.map((message,index)=><article className={'ai-chat-message '+message.role+(message.error?' failed':'')} key={index}>
          <div className="ai-chat-bubble">{message.role==='assistant'
            ? <Suspense fallback={<p>{message.content}</p>}><MarkdownAnswer content={message.content}/></Suspense>
            : <p>{message.content}</p>}</div>
          {message.reply&&<div className="ai-chat-citations">
            {message.reply.analytical_citations.map(id=>{
              const evidence=message.reply!.analytical_facts[id];
              return <details className="ai-chat-citation" key={id}><summary>Data · {id}</summary><pre>{JSON.stringify(evidence,null,2)}</pre></details>;
            })}
            {message.reply.knowledge_citations.map(id=>{
              const evidence=message.reply!.knowledge_chunks.find(chunk=>chunk.id===id);
              return <details className="ai-chat-citation knowledge" key={id}><summary>NASA · {id}</summary><p>{evidence?.text}</p></details>;
            })}
            {!!message.reply.scope_notes.length&&<details className="ai-chat-citation"><summary>Scope notes</summary><ul>{message.reply.scope_notes.map(note=><li key={note}>{note}</li>)}</ul></details>}
          </div>}
          {!!message.reply?.suggested_questions.length&&<div className="ai-chat-followups">{message.reply.suggested_questions.map(question=><button key={question} onClick={()=>void send(question)}>{question}</button>)}</div>}
        </article>)}
        {pending&&<div className="ai-chat-thinking" role="status"><span/><span/><span/> Gathering cited evidence</div>}
        <div ref={bottom}/>
      </div>
      {error&&<div className="ai-chat-error" role="alert"><span>{error}</span><button aria-label="Dismiss error" onClick={()=>setError('')}><X size={14}/></button></div>}
      <form className="ai-chat-compose" onSubmit={event=>{event.preventDefault();void send(draft);}}>
        <textarea aria-label="Ask IGNIS" placeholder="Ask about detections, sensors, or NASA FIRMS…" rows={2}
          value={draft} maxLength={4000} disabled={pending} onChange={event=>setDraft(event.target.value)}
          onKeyDown={event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();void send(draft);}}}/>
        <button type="submit" aria-label="Send message" title="Send message" disabled={pending||!draft.trim()}><Send size={17}/></button>
      </form>
    </section>}
  </div>;
}
