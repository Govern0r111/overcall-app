import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import AuthPage from "./AuthPage";

const renderLogin = (path = "/login") =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/issues" element={<p>Issues destination</p>} />
        <Route path="/app" element={<p>App destination</p>} />
      </Routes>
    </MemoryRouter>,
  );

describe("AuthPage", () => {
  it("requires an eight-character password", async () => {
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText("Email"), "person@example.com");
    await user.type(screen.getByLabelText("Password"), "short");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByText("Use at least 8 characters.")).toBeInTheDocument();
  });

  it("uses the safe local next path after continuing as a demo", async () => {
    const user = userEvent.setup();
    renderLogin("/login?next=%2Fissues%3Fseverity%3Dwarning");
    await user.click(screen.getByRole("button", { name: "Continue as demo" }));
    expect(await screen.findByText("Issues destination")).toBeInTheDocument();
  });
});
