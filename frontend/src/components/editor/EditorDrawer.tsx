/** The one drawer pattern for every entity editor: shadcn Sheet from the
 * right, native inputs inside a form so Enter saves, Esc closes (Radix default),
 * Verwijderen behind a confirm dialog. Focus returns to the opener automatically —
 * Radix restores focus to the element that was focused before open. */
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
  const [confirming, setConfirming] = useState(false);
  const [incomplete, setIncomplete] = useState(0);
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {/* Full-screen editor on mobile (the shadcn default is w-3/4, set via a data-side
          variant that a plain w-full won't override), capped at max-w-md from sm up. */}
      <SheetContent
        side="right"
        className="overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-md"
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
          className="flex min-h-full flex-col"
        >
          <SheetHeader>
            <SheetTitle className="font-display">{title}</SheetTitle>
          </SheetHeader>
          <div className="flex-1 space-y-4 px-4 pb-4">{children}</div>
          {(error || incomplete > 0) && (
            <p role="alert" className="px-4 pb-2 text-sm text-brick">
              {error ??
                (incomplete === 1
                  ? t("editor.incomplete")
                  : t("editor.incompleteMany").replaceAll("{n}", String(incomplete)))}
            </p>
          )}
          <SheetFooter className="flex-row items-center gap-2">
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
