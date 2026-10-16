import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/hooks/useAuth";
import { useAuth } from "@/hooks/auth-context";
import { SkyApi, type SkyUserPrincipal } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, SkyApi: { ...actual.SkyApi, me: vi.fn(), login: vi.fn() } };
});

const user = { id: "admin-id", username: "admin", role: "admin" };
const principal: SkyUserPrincipal = { type: "user", ...user, scopes: ["admin"] };

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => { resolve = resolvePromise; reject = rejectPromise; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  vi.mocked(SkyApi.login).mockResolvedValue({ token: "new-token", user });
});

describe("authentication request races", () => {
  it("does not restore a session after sign out while initial lookup is pending", async () => {
    localStorage.setItem("skyweaver_token", "old-token");
    const lookup = deferred<SkyUserPrincipal>();
    vi.mocked(SkyApi.me).mockReturnValue(lookup.promise);
    const { result } = renderHook(useAuth, { wrapper: AuthProvider });
    await act(() => result.current.signOut());
    await act(async () => { lookup.resolve(principal); await lookup.promise; });
    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it("does not clear a new session when an older lookup fails", async () => {
    localStorage.setItem("skyweaver_token", "old-token");
    const oldLookup = deferred<SkyUserPrincipal>();
    vi.mocked(SkyApi.me).mockReturnValueOnce(oldLookup.promise).mockResolvedValueOnce(principal);
    const { result } = renderHook(useAuth, { wrapper: AuthProvider });
    await act(() => result.current.signIn("admin", "password"));
    await act(async () => { oldLookup.reject(new Error("old token expired")); });
    expect(result.current.user?.id).toBe(user.id);
    expect(result.current.token).toBe("new-token");
    expect(localStorage.getItem("skyweaver_token")).toBe("new-token");
  });

  it("does not resurrect an in-progress sign in after sign out", async () => {
    const lookup = deferred<SkyUserPrincipal>();
    vi.mocked(SkyApi.me).mockReturnValue(lookup.promise);
    const { result } = renderHook(useAuth, { wrapper: AuthProvider });
    let signingIn!: Promise<void>;
    await act(async () => { signingIn = result.current.signIn("admin", "password"); });
    expect(localStorage.getItem("skyweaver_token")).toBe("new-token");
    await act(() => result.current.signOut());
    await act(async () => { lookup.resolve(principal); await signingIn; });
    expect(result.current.user).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(localStorage.getItem("skyweaver_token")).toBeNull();
  });

  it("finishes loading and clears credentials when session restoration fails", async () => {
    localStorage.setItem("skyweaver_token", "expired-token");
    vi.mocked(SkyApi.me).mockRejectedValue(new Error("expired"));
    const { result } = renderHook(useAuth, { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toBeNull();
    expect(localStorage.getItem("skyweaver_token")).toBeNull();
  });

  it("clears a newly issued token when the principal lookup fails", async () => {
    vi.mocked(SkyApi.me).mockRejectedValue(new Error("unable to read principal"));
    const { result } = renderHook(useAuth, { wrapper: AuthProvider });
    await act(async () => { await expect(result.current.signIn("admin", "password")).rejects.toThrow("unable to read principal"); });
    expect(result.current.loading).toBe(false);
    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem("skyweaver_token")).toBeNull();
  });

  it("does not store credentials when a pending sign in finishes after unmount", async () => {
    const login = deferred<Awaited<ReturnType<typeof SkyApi.login>>>();
    vi.mocked(SkyApi.login).mockReturnValue(login.promise);
    const { result, unmount } = renderHook(useAuth, { wrapper: AuthProvider });
    let signingIn!: Promise<void>;
    act(() => { signingIn = result.current.signIn("admin", "password"); });
    unmount();
    login.resolve({ token: "late-token", user });
    await signingIn;
    expect(localStorage.getItem("skyweaver_token")).toBeNull();
    expect(SkyApi.me).not.toHaveBeenCalled();
  });
});
