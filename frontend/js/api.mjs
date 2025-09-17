export async function getModels(){
  try{
    const r = await fetch("/api/models");
    return await r.json();
  }catch(e){
    console.error("[API] models error", e);
    return {ok:false, error:String(e)};
  }
}

export async function processFile(file, model, onProgress){
  const fd = new FormData();
  fd.append("file", file);
  fd.append("model", model);
  try{
    const r = await fetch("/api/process", { method:"POST", body: fd });
    return await r.json();
  }catch(e){
    console.error("[API] process error", e);
    return {ok:false, error:String(e)};
  }
}
