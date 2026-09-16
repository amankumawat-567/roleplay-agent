import { useNavigate } from "react-router-dom";
import { useAppStore } from "../stores/useAppStore";

/** Creates a session for a persona and navigates to its chat page - shared
 * by every page that renders a persona card (Home, Explore, Tags, Library).
 * `voice: true` lands directly on VoiceCallPage instead of ChatPage -
 * no `autoStart` router state needed for that destination, since
 * VoiceCallPage generates a starter:"ai" persona's opening turn itself
 * (see its own mount effect) rather than relying on ChatPage having
 * already done so first. */
export function useStartChat() {
  const createSession = useAppStore((s) => s.createSession);
  const navigate = useNavigate();

  return async function startChat(gameId: string, opts?: { voice?: boolean }) {
    const { sessionId, starter } = await createSession(gameId);
    if (opts?.voice) {
      navigate(`/chat/${sessionId}/voice`);
      return;
    }
    navigate(`/chat/${sessionId}`, { state: { autoStart: starter === "ai" } });
  };
}
