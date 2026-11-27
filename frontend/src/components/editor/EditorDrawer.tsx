/** Controlled editors have no trigger to restore focus to. Closing restores the
 * opener, or the main content after the opener is removed. */
import { type ReactNode, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useT } from "../../lib/i18n";

export interface EditorDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  saving: boolean;
  /** Non-field error (parseApiError().general), rendered above the footer. */
  error: string | null;
  onSubmit: () => void;
  /** When set, renders "Verwijderen…" with a confirm dialog. */
  onDelete?: () => void;
  /** Extra submit-row button — "opslaan + nog een" on create drawers. */
  submitExtra?: ReactNode;
  children: ReactNode;
}

export function EditorDrawer({
  open,
  onOpenChange,
  title,
  saving,
  error,
  onSubmit,
  onDelete,
  submitExtra,
  children,
}: EditorDrawerProps) {
  const t = useT();
  // Child inputs autofocus before Radix emits its opening event.
  const [opener] = useState(() => document.activeElement as HTMLElement | null);
  const [confirming, setConfirming] = useState(false);
  const [incomplete, setIncomplete] = useState(0);
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {/* Full-screen editor on mobile (the shadcn default is w-3/4, set via a data-side
          variant that a plain w-full won't override), capped at max-w-md from sm up. */}
      <SheetContent
        side="right"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          // A mouse click in Safari and macOS Firefox does not focus a button, so the
          // opener can be <body>, where focus would be lost.
          const target =
            opener && opener !== document.body && opener.isConnected
              ? opener
              : document.querySelector<HTMLElement>("main");
          target?.focus();
        }}
        className="data-[side=right]:w-full data-[side=right]:sm:max-w-md [@media(height<24rem)]:overflow-y-auto"
      >
        <form
          // noValidate kills the browser's own validation bubble, which arrived in English
          // regardless of locale, styled by the OS, and anchored to nothing. checkValidity
          // still runs — we just report the result ourselves, in the drawer's own language.
          noValidate
          // The count drives the plural in the alert; the attribute drives the CSS that
          // turns every still-empty required field's border brick (index.css), so the
          // "highlighted" the copy promises is a mark of its own, not the focus ring.
          data-incomplete={incomplete > 0 || undefined}
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            if (!form.checkValidity()) {
              const invalid = form.querySelectorAll<HTMLElement>(
                ":is(input, select, textarea):invalid",
              );
              invalid[0]?.focus();
              setIncomplete(invalid.length);
              return;
            }
            setIncomplete(0);
            onSubmit();
          }}
          className="flex min-h-0 flex-1 flex-col [@media(height<24rem)]:min-h-full [@media(height<24rem)]:flex-none"
        >
          <SheetHeader className="shrink-0 pr-16">
            <SheetTitle className="font-display">{title}</SheetTitle>
          </SheetHeader>
          {/* A wrapped footer can fill a short viewport. Scroll the entire sheet there. */}
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 pb-4 [@media(height<24rem)]:overflow-visible">
            {children}
          </div>
          {(error || incomplete > 0) && (
            <p role="alert" className="px-4 pb-2 text-sm text-brick">
              {error ??
                (incomplete === 1
                  ? t("editor.incomplete")
                  : t("editor.incompleteMany").replaceAll("{n}", String(incomplete)))}
            </p>
          )}
          <SheetFooter className="flex shrink-0 flex-row flex-wrap items-center justify-end gap-2 border-t border-border pb-[max(1rem,env(safe-area-inset-bottom))]">
            {onDelete && (
              <Button
                type="button"
                onClick={() => setConfirming(true)}
                variant="link"
                className="mr-auto text-destructive"
              >
                {t("editor.delete")}…
              </Button>
            )}
            <Button type="button" onClick={() => onOpenChange(false)} variant="outline">
              {t("editor.cancel")}
            </Button>
            {submitExtra}
            <Button type="submit" disabled={saving}>
              {t("editor.save")}
            </Button>
          </SheetFooter>
        </form>
        {onDelete && (
          <Dialog open={confirming} onOpenChange={setConfirming}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{t("editor.deleteConfirmTitle")}</DialogTitle>
                <DialogDescription>{t("editor.deleteConfirmBody")}</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button type="button" onClick={() => setConfirming(false)} variant="outline">
                  {t("editor.cancel")}
                </Button>
                <Button
                  type="button"
                  onClick={() => {
                    setConfirming(false);
                    onDelete();
                  }}
                  variant="destructive"
                >
                  {t("editor.delete")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </SheetContent>
    </Sheet>
  );
}
