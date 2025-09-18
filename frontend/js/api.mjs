async function safeFetch(url, options){
  try{
    const res = await fetch(url, options);
    const data = await res.json();
    data.httpStatus = res.status;
    return data;
  }catch(err){
    console.error(`[API] ${url} error`, err);
    return {ok:false, error:String(err)};
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

export async function preprocessDocument(sessionId, model){
  return safeFetch("/api/preprocess", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({session_id:sessionId, model})
  });
}

export async function determineHeaders(sessionId, model){
  return safeFetch("/api/determine-headers", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({session_id:sessionId, model})
  });
}

export async function processPasses(sessionId, model){
  return safeFetch("/api/process", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({session_id:sessionId, model})
  });
}

export async function testLLM(model){
  return safeFetch("/api/llm-test", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({model})
  });
}
