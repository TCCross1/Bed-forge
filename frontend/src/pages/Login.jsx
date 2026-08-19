import React,{useState} from "react";
import {useNavigate} from "react-router-dom";
import {useAuth} from "../context/AuthContext";

const DEMO_USERS=[{label:"Plant Admin",email:"admin@bedforge.com",password:"admin123"},{label:"Supervisor",email:"supervisor@bedforge.com",password:"super123"},{label:"QC Tech",email:"qc@bedforge.com",password:"qc123"},{label:"Production",email:"production@bedforge.com",password:"prod123"}];

export default function Login(){
 const navigate=useNavigate();
 const {login}=useAuth();
 const [email,setEmail]=useState("");
 const [password,setPassword]=useState("");
 const [error,setError]=useState("");
 const [busy,setBusy]=useState(false);
 const handleSubmit=async(e)=>{e.preventDefault();setError("");setBusy(true);try{await login(email.trim(),password);navigate("/");}catch(err){setError(err?.message||"Sign-in failed");}finally{setBusy(false);}};
 const demoLogin=async(user)=>{setEmail(user.email);setPassword(user.password);setError("");setBusy(true);try{await login(user.email,user.password);navigate("/");}catch(err){setError(err?.message||"Demo sign-in failed");}finally{setBusy(false);}};
 return (
  <div className="min-h-screen w-full flex bg-[#0A0C10] text-white">
   <div className="relative hidden md:flex md:w-1/2 lg:w-[55%] overflow-hidden bg-black">
    <img src="/brand/login-hero.jpg" alt="Prestress hardware" className="absolute inset-0 w-full h-full object-cover" />
   </div>
   <div className="w-full md:w-1/2 lg:w-[45%] flex items-center justify-center p-6 sm:p-10">
    <div className="w-full max-w-md">
     <div className="mb-8">
      <img src="/brand/bedforge-logo.jpg" alt="BedForge" className="h-40 w-auto max-w-[520px] mb-4 object-contain" />
      <div className="text-2xl font-bold tracking-wide" style={{color:"#2979FF"}}>QUALITY CONTROL</div>
      <div className="text-xs tracking-[0.25em] text-white/50 mt-2">SECURE ACCESS</div>
     </div>
     <form onSubmit={handleSubmit} className="space-y-4">
      <div>
       <label className="block text-xs tracking-widest text-white/50 mb-2">EMAIL</label>
       <input type="email" value={email} onChange={(e)=>setEmail(e.target.value)} className="w-full rounded-md bg-[#12151C] border border-white/10 px-3 py-3 outline-none focus:border-[#2979FF]" />
      </div>
      <div>
       <label className="block text-xs tracking-widest text-white/50 mb-2">PASSWORD</label>
       <input type="password" value={password} onChange={(e)=>setPassword(e.target.value)} className="w-full rounded-md bg-[#12151C] border border-white/10 px-3 py-3 outline-none focus:border-[#2979FF]" />
      </div>
      {error?<div className="text-sm text-red-400 border border-red-500/30 rounded-md px-3 py-2">{error}</div>:null}
      <button type="submit" disabled={busy} className="w-full rounded-md bg-[#2979FF] hover:bg-[#3b86ff] disabled:opacity-60 font-semibold py-3 transition">{busy?"SIGNING IN...":"SIGN IN"}</button>
     </form>
     <div className="mt-8">
      <div className="text-xs tracking-widest text-white/40 mb-3">QUICK DEMO LOGIN</div>
      <div className="grid grid-cols-2 gap-2">
       {DEMO_USERS.map((u)=>(
        <button key={u.label} type="button" disabled={busy} onClick={()=>demoLogin(u)} className="rounded-md border border-white/10 bg-white/5 hover:bg-white/10 py-3 text-sm transition">{u.label}</button>
       ))}
      </div>
     </div>
    </div>
   </div>
  </div>
 );
}
