import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { LandingPage } from "./LandingPage";

function renderLanding() {
  return render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>,
  );
}

describe("landing page", () => {
  it("renders the main sections and links to signup and the demo", () => {
    renderLanding();

    expect(screen.getByRole("heading", { level: 1, name: /see where your api money goes/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /one small change/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /questions, answered/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /try the demo/i })).toHaveAttribute("href", "/app");
    expect(screen.getByRole("link", { name: "Sign up" })).toHaveAttribute("href", "/signup");
    expect(screen.getAllByText("Experimental")).toHaveLength(2);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("opens an FAQ with the keyboard", async () => {
    const user = userEvent.setup();
    renderLanding();

    const summary = screen.getByText(/do you store my prompts or request bodies/i);
    await user.click(summary);
    expect(summary.closest("details")).toHaveAttribute("open");
  });

  it("exposes a working three-choice theme group", () => {
    renderLanding();
    const group = screen.getByRole("group", { name: "Color theme" });
    const darkButton = within(group).getByRole("button", { name: "Use dark theme" });
    fireEvent.click(darkButton);

    expect(darkButton).toHaveAttribute("aria-pressed", "true");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
