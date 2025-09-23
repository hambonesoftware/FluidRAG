
function describeBody(body){
  if(!body) return null;
  if(body instanceof FormData){
    const summary = {};
    for(const [key, value] of body.entries()){
      if(value instanceof File){
        summary[key] = {
          kind: "file",
          name: value.name,
          size: value.size,
          type: value.type
        };
      }else{
        summary[key] = {kind: "value", value};
      }
    }
    return summary;
  }
  if(typeof body === "string"){
    try{
      return {kind:"json", value: JSON.parse(body)};
    }catch{
      return {kind:"text", value: body};
    }
  }
  return body;
}

async function safeFetch(url, options){
  const method = options?.method || "GET";
  console.groupCollapsed(`[API] Request ${method} ${url}`);
  if(options){
    if(options.headers) console.log("Headers", options.headers);
    if(Object.prototype.hasOwnProperty.call(options, "body")){
      console.log("Body", describeBody(options.body));
    }
  }
  console.groupEnd();
  try{
    const res = await fetch(url, options);
    let data;
    try{
      data = await res.json();
    }catch(err){
      console.warn(`[API] ${url} JSON parse error`, err);
      data = {ok:false, error:"Invalid JSON response"};
    }
    data.httpStatus = res.status;
    console.groupCollapsed(`[API] Response ${res.status} ${url}`);
    console.log("Headers", Object.fromEntries(res.headers.entries()));
    console.log("Body", data);
    console.groupEnd();

    return data;
  }catch(err){
    console.error(`[API] ${url} error`, err);
    const message = (() => {
      if(err instanceof TypeError){
        const text = String(err?.message || err);
        if(text.toLowerCase().includes("failed to fetch")){
          return "Network error: unable to reach the FluidRAG backend. Confirm the server is running and accessible.";
        }
        return text;
      }
      return String(err);
    })();
    return {ok:false, error:message, httpStatus:0, networkError:true};
  }
}

export async function getModels(){
  return safeFetch("/api/models");
}

export async function uploadDocument(file){
  const fd = new FormData();
  fd.append("file", file);
  return safeFetch("/api/upload", {method:"POST", body:fd});
}


export async function preprocessDocument(sessionId, model, provider){
  return safeFetch("/api/preprocess", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({session_id:sessionId, model, provider})
  });
}

export async function determineHeaders(sessionId, model, provider){
  return safeFetch("/api/determine-headers", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({session_id:sessionId, model, provider})
  });
}

export async function determineLocalHeaders(sessionId){
  return safeFetch("/api/pdf/headers/session", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({session_id:sessionId})
  });
}

export async function processPasses(sessionId, model, provider, options={}){
  const payload = {
    session_id:sessionId,
    model,
    provider,
    only_mechanical:false,
    debug:true,
    debug_llm_io:true
  };
  if(options && options.forceRefresh){
    payload.force_refresh = true;
  }
  if(options && options.passes){
    payload.passes = options.passes;
  }
  return safeFetch("/api/process", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(payload)
  });
}

export async function testLLM(model, provider){
  return safeFetch("/api/llm-test", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({model, provider})

  });
}
