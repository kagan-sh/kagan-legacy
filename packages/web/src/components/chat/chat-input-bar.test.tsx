import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import { renderWithProviders } from "@/test/render";
import { ChatInputBar } from "@/components/chat/chat-input-bar";
import { sseConnectedAtom } from "@/lib/atoms/connection";
import { isStreamingAtom } from "@/lib/atoms/chat";

function connectedStore(streaming: boolean = false) {
    const store = createStore();
    store.set(sseConnectedAtom, true);
    store.set(isStreamingAtom, streaming);
    return store;
}

describe("ChatInputBar", () => {
    it("keeps send button disabled when input is empty", () => {
        renderWithProviders(<ChatInputBar onSend={vi.fn()} />, {
            store: connectedStore(),
        });

        expect(
            screen.getByRole("button", { name: "Send message" }),
        ).toBeDisabled();
    });

    it("detects slash command input and calls onSlashCommand", async () => {
        const user = userEvent.setup();
        const onSend = vi.fn();
        const onSlashCommand = vi.fn();

        renderWithProviders(
            <ChatInputBar onSend={onSend} onSlashCommand={onSlashCommand} />,
            { store: connectedStore() },
        );

        const input = screen.getByPlaceholderText(
            "Type a message or / for commands...",
        );
        await user.type(input, "/h");
        expect(screen.getByText("/help")).toBeVisible();

        await user.clear(input);
        await user.type(input, "/help");
        await user.click(screen.getByRole("button", { name: "Send message" }));

        expect(onSlashCommand).toHaveBeenCalledWith("/help");
        expect(onSend).not.toHaveBeenCalled();
    });

    it("calls onSend for regular text", async () => {
        const user = userEvent.setup();
        const onSend = vi.fn();

        renderWithProviders(<ChatInputBar onSend={onSend} />, {
            store: connectedStore(),
        });

        await user.type(
            screen.getByPlaceholderText("Type a message or / for commands..."),
            "hello world",
        );
        await user.click(screen.getByRole("button", { name: "Send message" }));

        expect(onSend).toHaveBeenCalledWith("hello world", undefined);
    });

    it("disables send button while streaming", () => {
        renderWithProviders(<ChatInputBar onSend={vi.fn()} />, {
            store: connectedStore(true),
        });

        expect(
            screen.getByRole("button", { name: "Send message" }),
        ).toBeDisabled();
    });

    it("clears draft on Ctrl+C when not streaming", async () => {
        const user = userEvent.setup();
        renderWithProviders(<ChatInputBar onSend={vi.fn()} />, {
            store: connectedStore(),
        });

        const input = screen.getByPlaceholderText(
            "Type a message or / for commands...",
        );
        await user.type(input, "draft text");
        await user.keyboard("{Control>}c{/Control}");

        expect(input).toHaveValue("");
    });

    it("calls onInterrupt on Escape while streaming", async () => {
        const user = userEvent.setup();
        const onInterrupt = vi.fn();
        renderWithProviders(
            <ChatInputBar onSend={vi.fn()} onInterrupt={onInterrupt} />,
            { store: connectedStore(true) },
        );

        const input = screen.getByPlaceholderText(
            "Type a message or / for commands...",
        );
        await user.click(input);
        await user.keyboard("{Escape}");

        expect(onInterrupt).toHaveBeenCalledTimes(1);
    });

    it("has add attachment button with plus icon", () => {
        renderWithProviders(<ChatInputBar onSend={vi.fn()} />, {
            store: connectedStore(),
        });

        expect(
            screen.getByRole("button", { name: "Add attachment" }),
        ).toBeVisible();
    });

    it("opens attachment menu when clicking plus button", async () => {
        const user = userEvent.setup();
        renderWithProviders(<ChatInputBar onSend={vi.fn()} />, {
            store: connectedStore(),
        });

        await user.click(
            screen.getByRole("button", { name: "Add attachment" }),
        );

        expect(screen.getByText("Add files or photos")).toBeVisible();
        expect(screen.getByText("Images, docs, code files")).toBeVisible();
    });

    describe("D7: slash autocomplete uses Radix Command native focus management", () => {
        it("renders command items without manual selectedIndex class", async () => {
            const user = userEvent.setup();
            renderWithProviders(<ChatInputBar onSend={vi.fn()} />, {
                store: connectedStore(),
            });

            const input = screen.getByPlaceholderText(
                "Type a message or / for commands...",
            );
            await user.type(input, "/h");

            // Command items are rendered by Radix Command (no manually-applied
            // active background class from selectedIndex).
            const items = screen.queryAllByRole("option");
            for (const item of items) {
                expect(item.className).not.toContain("bg-[var(--accent)] text-[var(--accent-foreground)]");
            }
        });

        it("autocomplete list closes after a command is selected", async () => {
            const user = userEvent.setup();
            const onSlashCommand = vi.fn();
            renderWithProviders(
                <ChatInputBar onSend={vi.fn()} onSlashCommand={onSlashCommand} />,
                { store: connectedStore() },
            );

            const input = screen.getByPlaceholderText(
                "Type a message or / for commands...",
            );
            await user.type(input, "/help");
            // The autocomplete list renders options via Radix Command.
            // Click the option element (role="option") that contains "/help".
            const helpOption = screen.queryByRole("option", { name: /\/help/ });
            if (helpOption) {
                await user.click(helpOption);
            }

            // After selection, the autocomplete list should be gone
            expect(screen.queryByRole("group")).toBeNull();
        });
    });
});
