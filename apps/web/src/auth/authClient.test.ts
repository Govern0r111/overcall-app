import { beforeEach, describe, expect, it } from "vitest";
import { authClient, SESSION_KEY } from "./authClient";

describe("demo auth client", () => {
  beforeEach(async () => {
    await authClient.logout();
  });

  it("creates and restores a local demo session without storing a password", async () => {
    const user = await authClient.continueAsDemo();
    expect(user.email).toBe("demo@overcall.local");
    expect(await authClient.me()).toMatchObject({ email: "demo@overcall.local" });
    expect(localStorage.getItem(SESSION_KEY)).not.toContain("password");
  });

  it("normalizes email addresses on demo sign-in", async () => {
    const user = await authClient.login("  USER@example.com ", "password-123");
    expect(user.email).toBe("user@example.com");
  });

  it("returns a helpful error for a rejected demo credential", async () => {
    await expect(authClient.login("wrong@example.com", "password-123")).rejects.toThrow(
      "That email and password do not match.",
    );
  });

  it("does not claim to send password reset email in demo mode", async () => {
    await expect(authClient.requestPasswordReset("user@example.com")).rejects.toThrow(
      "Password reset email is unavailable in demo mode.",
    );
  });
});
