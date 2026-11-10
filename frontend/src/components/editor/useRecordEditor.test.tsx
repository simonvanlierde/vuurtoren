/** The hook routes save to create or update by whether a record is being edited, and
 * only deletes an existing one. Run through a server render so no DOM is needed; the
 * mutations are fakes that record their calls. */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { type CrudApi, useRecordEditor } from "./useRecordEditor";

function Probe({ use }: { use: () => void }) {
  use();
  return null;
}

function setup(record: { id: number } | null) {
  const create = { mutate: vi.fn(), isError: false, isPending: false };
  const update = { mutate: vi.fn(), isError: false, isPending: true };
  const remove = { mutate: vi.fn(), isError: false, isPending: false };
  const api = {
    useCreate: () => create,
    useUpdate: () => update,
    useDelete: () => remove,
  } as unknown as CrudApi<string, string>;
  let editor!: ReturnType<typeof useRecordEditor<string, string>>;
  renderToStaticMarkup(
    <Probe
      use={() => {
        editor = useRecordEditor(api, record);
      }}
    />,
  );
  return { editor, create, update, remove };
}

describe("useRecordEditor", () => {
  it("creates and cannot delete when no record is edited", () => {
    const { editor, create, update, remove } = setup(null);
    const done = () => {};
    editor.save("body", done);
    editor.remove(done);
    expect(create.mutate).toHaveBeenCalledWith("body", { onSuccess: done });
    expect(update.mutate).not.toHaveBeenCalled();
    expect(remove.mutate).not.toHaveBeenCalled();
    expect(editor.saving).toBe(false);
  });

  it("updates and deletes the edited record", () => {
    const { editor, create, update, remove } = setup({ id: 7 });
    const done = () => {};
    editor.save("body", done);
    editor.remove(done);
    expect(update.mutate).toHaveBeenCalledWith({ id: 7, body: "body" }, { onSuccess: done });
    expect(remove.mutate).toHaveBeenCalledWith(7, { onSuccess: done });
    expect(create.mutate).not.toHaveBeenCalled();
    expect(editor.saving).toBe(true);
  });
});
