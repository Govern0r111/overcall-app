import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, Chrome, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { authClient } from "../auth/authClient";
import { safeRedirect } from "../auth/safeRedirect";
import { authConfigError, hasSupabase } from "../lib/supabase";

type Mode = "login" | "signup" | "forgot" | "reset";
type Values = { email?: string; password?: string; confirm?: string };

const makeSchema = (mode: Mode) =>
  z
    .object({
      email: z.string().trim().email("Enter a valid email address."),
      password: z.string().optional(),
      confirm: z.string().optional(),
    })
    .superRefine((values, context) => {
      if (mode === "forgot") return;
      if (!values.password || values.password.length < 8) {
        context.addIssue({
          code: "custom",
          path: ["password"],
          message: "Use at least 8 characters.",
        });
      }
      if ((mode === "signup" || mode === "reset") && values.password !== values.confirm) {
        context.addIssue({
          code: "custom",
          path: ["confirm"],
          message: "Passwords do not match.",
        });
      }
    });

export default function AuthPage({ mode }: { mode: Mode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [showPassword, setShowPassword] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const schema = makeSchema(mode);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "", confirm: "" } });

  const title = {
    login: "Welcome back",
    signup: "Create your workspace",
    forgot: "Reset your password",
    reset: "Choose a new password",
  }[mode];
  const next = safeRedirect(searchParams.get("next") ?? (location.state as { from?: string } | null)?.from);

  const submit = async (values: Values) => {
    setError("");
    setMessage("");
    const email = values.email?.trim().toLowerCase() ?? "";
    try {
      if (mode === "forgot") {
        await authClient.requestPasswordReset(email);
        setMessage("If an account exists, a password reset link is on its way.");
        return;
      }
      if (mode === "reset") {
        await authClient.updatePassword(values.password ?? "");
        setMessage("Your password has been updated. You can now sign in.");
        return;
      }
      if (mode === "signup") {
        const result = await authClient.signup(email, values.password ?? "");
        if (result.needsEmailConfirmation) {
          setMessage("Check your email to confirm your account before signing in.");
          return;
        }
      } else {
        await authClient.login(email, values.password ?? "");
      }
      navigate(next, { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Something went wrong. Please try again.");
    }
  };

  const signInWithGoogle = async () => {
    setError("");
    try {
      await authClient.loginWithGoogle();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Google sign-in failed. Please try again.");
    }
  };

  const continueAsDemo = async () => {
    setError("");
    try {
      await authClient.continueAsDemo();
      navigate(next, { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Demo mode is unavailable.");
    }
  };

  const fieldError = (id: string, text?: string) =>
    text ? (
      <span id={`${id}-error`} className="mt-1 block text-xs text-destructive">
        {text}
      </span>
    ) : null;
  const passwordModes = mode !== "forgot";

  return (
    <main id="main-content" tabIndex={-1} className="grid min-h-screen bg-background text-foreground lg:grid-cols-2">
      <section className="hidden bg-primary p-12 text-primary-foreground lg:flex lg:flex-col lg:justify-between">
        <Link to="/" className="flex items-center gap-2 font-semibold">
          <ShieldCheck className="h-5 w-5" /> Overcall
        </Link>
        <div>
          <p className="max-w-md text-4xl font-semibold leading-tight">Make every API request earn its place.</p>
          <p className="mt-5 max-w-md text-sm leading-6 text-primary-foreground/70">
            A quiet, useful view of waste hiding in your provider bill.
          </p>
        </div>
        <p className="text-xs text-primary-foreground/60">Free during beta</p>
      </section>

      <section className="flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <Link to="/" className="mb-10 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" /> Back to home
          </Link>
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {mode === "login"
              ? "Sign in to your account or continue with a local demo."
              : mode === "signup"
                ? "Start with Google or create an account."
                : mode === "forgot"
                  ? "We’ll send a reset link if the account exists."
                  : "Enter and confirm your new password."}
          </p>
          {authConfigError && <p className="mt-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{authConfigError}</p>}

          {passwordModes && hasSupabase && (
            <>
              <button
                type="button"
                onClick={signInWithGoogle}
                className="mt-7 flex h-11 w-full items-center justify-center gap-2 rounded-md border border-border bg-card text-sm font-medium hover:bg-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
              >
                <Chrome className="h-4 w-4" /> Continue with Google
              </button>
              <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground">
                <span className="h-px flex-1 bg-border" />
                <span>or use email</span>
                <span className="h-px flex-1 bg-border" />
              </div>
            </>
          )}

          <form onSubmit={handleSubmit(submit)} className="space-y-5" noValidate>
            {mode !== "reset" && (
              <label className="block text-sm font-medium" htmlFor="email">
                Email
                <input
                  {...register("email")}
                  id="email"
                  type="email"
                  autoComplete="email"
                  aria-invalid={Boolean(errors.email)}
                  aria-describedby={errors.email ? "email-error" : undefined}
                  className="mt-2 h-11 w-full rounded-md border border-input bg-card px-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                  placeholder="you@example.com"
                />
                {fieldError("email", errors.email?.message)}
              </label>
            )}

            {passwordModes && (
              <label className="block text-sm font-medium" htmlFor="password">
                {mode === "reset" ? "New password" : "Password"}
                <div className="relative mt-2">
                  <input
                    {...register("password")}
                    id="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                    aria-invalid={Boolean(errors.password)}
                    aria-describedby={errors.password ? "password-error" : undefined}
                    className="h-11 w-full rounded-md border border-input bg-card px-3 pr-11 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                    placeholder="At least 8 characters"
                  />
                  <button
                    type="button"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                    onClick={() => setShowPassword((shown) => !shown)}
                    className="absolute right-3 top-3 text-muted-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {fieldError("password", errors.password?.message)}
              </label>
            )}

            {(mode === "signup" || mode === "reset") && (
              <label className="block text-sm font-medium" htmlFor="confirm">
                Confirm password
                <input
                  {...register("confirm")}
                  id="confirm"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  aria-invalid={Boolean(errors.confirm)}
                  aria-describedby={errors.confirm ? "confirm-error" : undefined}
                  className="mt-2 h-11 w-full rounded-md border border-input bg-card px-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                />
                {fieldError("confirm", errors.confirm?.message)}
              </label>
            )}

            {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>}
            {message && <p className="rounded-md bg-primary/10 px-3 py-2 text-sm" role="status">{message}</p>}
            {!message && (
              <button
                disabled={isSubmitting}
                className="h-11 w-full rounded-md bg-primary text-sm font-medium text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                {isSubmitting
                  ? "Please wait…"
                  : mode === "login"
                    ? "Log in"
                    : mode === "signup"
                      ? "Create account"
                      : mode === "forgot"
                        ? "Send reset link"
                        : "Update password"}
              </button>
            )}
          </form>

          {mode === "login" && (
            <div className="mt-4 flex justify-between text-sm">
              <Link to="/forgot" className="text-primary hover:underline">Forgot password?</Link>
              <Link to="/signup" className="text-primary hover:underline">Create an account</Link>
            </div>
          )}
          {mode === "signup" && (
            <p className="mt-5 text-center text-sm text-muted-foreground">
              Already have an account? <Link to="/login" className="text-primary hover:underline">Log in</Link>
            </p>
          )}
          {(mode === "forgot" || mode === "reset") && (
            <p className="mt-5 text-sm text-muted-foreground">
              Remembered it? <Link to="/login" className="text-primary hover:underline">Back to log in</Link>
            </p>
          )}
          {passwordModes && !hasSupabase && !authConfigError && (
            <button
              type="button"
              onClick={continueAsDemo}
              className="mt-6 h-11 w-full rounded-md border border-border text-sm font-medium hover:bg-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
            >
              Continue as demo
            </button>
          )}
        </div>
      </section>
    </main>
  );
}
