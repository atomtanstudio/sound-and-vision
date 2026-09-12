import type { SongForm } from "./model";

export type DescriptionSource = Pick<SongForm, "description" | "style">;
export function descriptionMatches(
  form: DescriptionSource,
  source: DescriptionSource,
) {
  return form.description === source.description && form.style === source.style;
}
export function applyDescription(
  form: SongForm,
  source: DescriptionSource,
  description: string,
) {
  return descriptionMatches(form, source)
    ? { ...form, description, style: "" }
    : form;
}
