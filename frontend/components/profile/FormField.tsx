// Re-exported from the shared location (components/ui/Field.tsx) now that
// every page uses the same form-control styling, not just Profile's
// sub-forms. Kept here so the existing relative imports across
// components/profile/*Section.tsx don't all need touching.
export { FormField, inputClass, textareaClass, selectClass, Select } from "@/components/ui/Field";
