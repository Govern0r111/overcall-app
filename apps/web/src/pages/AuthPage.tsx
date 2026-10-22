import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, Chrome, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";
import { authClient } from "../auth/authClient";
import { supabase } from "../lib/supabase";

type Mode = "login" | "signup" | "forgot";
const schemas = {
  login: z.object({ email: z.string().email("Enter a valid email address"), password: z.string().min(6, "Use at least 6 characters") }),
  signup: z.object({ email: z.string().email("Enter a valid email address"), password: z.string().min(6, "Use at least 6 characters"), confirm: z.string() }).refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match" }),
  forgot: z.object({ email: z.string().email("Enter a valid email address") }),
};

export default function AuthPage({ mode }: { mode: Mode }) {
  const navigate = useNavigate();
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const schema = schemas[mode];
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<any>({ resolver: zodResolver(schema) });
  const title = mode === "login" ? "Welcome back" : mode === "signup" ? "Create your workspace" : "Reset your password";

  const submit = async (values: any) => {
    setError("");
    try {
      if (mode === "forgot") {
        if (supabase) {
          const { error } = await supabase.auth.resetPasswordForEmail(values.email, { redirectTo: `${window.location.origin}/login` });
          if (error) throw error;
        }
        setError("If an account exists, we’ll send a reset link shortly.");
        return;
      }
      await (mode === "login" ? authClient.login(values.email, values.password) : authClient.signup(values.email, values.password));
      navigate("/app", { replace: true });
    } catch (e) { setError(e instanceof Error ? e.message : "Something went wrong. Please try again."); }
  };

  const signInWithGoogle = async () => {
    setError("");
    try {
      await authClient.loginWithGoogle();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Google sign-in failed. Please try again.");
    }
  };

  return <main className="grid min-h-screen bg-background text-foreground lg:grid-cols-2"><section className="hidden bg-primary p-12 text-primary-foreground lg:flex lg:flex-col lg:justify-between"><Link to="/" className="flex items-center gap-2 font-semibold"><ShieldCheck className="h-5 w-5" /> Overcall</Link><div><p className="max-w-md text-4xl font-semibold leading-tight">Make every API request earn its place.</p><p className="mt-5 max-w-md text-sm leading-6 text-primary-foreground/70">A quiet, useful view of waste hiding in your provider bill.</p></div><p className="text-xs text-primary-foreground/60">Free during beta</p></section><section className="flex items-center justify-center p-6"><div className="w-full max-w-md"><Link to="/" className="mb-12 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" /> Back to home</Link><h1 className="text-3xl font-semibold tracking-tight">{title}</h1><p className="mt-2 text-sm text-muted-foreground">{mode === "login" ? "Use your demo session or sign in below." : mode === "signup" ? "Start with Google or create an account." : "We’ll help you get back into your workspace."}</p>{mode !== "forgot" && supabase && <><button type="button" onClick={signInWithGoogle} className="mt-8 flex h-11 w-full items-center justify-center gap-2 rounded-md border border-border bg-card text-sm font-medium hover:bg-accent"><Chrome className="h-4 w-4" /> Continue with Google</button><div className="my-5 flex items-center gap-3 text-xs text-muted-foreground"><span className="h-px flex-1 bg-border" /><span>or use email</span><span className="h-px flex-1 bg-border" /></div></>}<form onSubmit={handleSubmit(submit)} className={mode !== "forgot" && supabase ? "space-y-5" : "mt-8 space-y-5"}><label className="block text-sm font-medium">Email<input {...register("email")} type="email" autoComplete="email" className="mt-2 h-11 w-full rounded-md border border-input bg-card px-3 text-sm" placeholder="you@example.com" />{errors.email && <FieldError text={String(errors.email.message)} />}</label>{mode !== "forgot" && <><label className="block text-sm font-medium">Password<div className="relative mt-2"><input {...register("password")} type={showPassword ? "text" : "password"} autoComplete={mode === "login" ? "current-password" : "new-password"} className="h-11 w-full rounded-md border border-input bg-card px-3 pr-10 text-sm" placeholder="At least 6 characters" /><button type="button" aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-3 text-muted-foreground">{showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button></div>{errors.password && <FieldError text={String(errors.password.message)} />}</label>{mode === "signup" && <label className="block text-sm font-medium">Confirm password<input {...register("confirm")} type={showPassword ? "text" : "password"} className="mt-2 h-11 w-full rounded-md border border-input bg-card px-3 text-sm" />{errors.confirm && <FieldError text={String(errors.confirm.message)} />}</label>}</>}{error && <p className="rounded-md bg-primary/10 px-3 py-2 text-sm text-primary" role="status">{error}</p>}<button disabled={isSubmitting} className="h-11 w-full rounded-md bg-primary text-sm font-medium text-primary-foreground hover:opacity-90">{mode === "login" ? "Log in" : mode === "signup" ? "Create workspace" : "Send reset link"}</button></form>{mode === "login" && <div className="mt-4 flex justify-between text-sm"><Link to="/forgot" className="text-primary hover:underline">Forgot password?</Link><Link to="/signup" className="text-primary hover:underline">Create an account</Link></div>  }{mode !== "forgot" && !supabase && <button onClick={async () => { await authClient.signup("demo@overcall.local", "demo-password"); navigate("/app", { replace: true }); }} className="mt-6 h-11 w-full rounded-md border border-border text-sm font-medium hover:bg-accent">Continue as demo</button>}{mode === "forgot" && <p className="mt-5 text-sm text-muted-foreground">Remembered it? <Link to="/login" className="text-primary hover:underline">Back to log in</Link></p>}</div></section></main>;
}

function FieldError({ text }: { text: string }) { return <span className="mt-1 block text-xs text-primary">{text}</span>; }
