<script setup lang="ts">
import { computed } from 'vue';
import { Badge } from '@coneva-cev/storybook/badge';

const props = defineProps<{
  pdfFiles: File[];
  mappingFile: File | null;
}>();

const emit = defineEmits<{
  (e: 'update:pdfFiles', v: File[]): void;
  (e: 'update:mappingFile', v: File | null): void;
}>();

function fileKey(f: File): string {
  const path = (f as File & { webkitRelativePath?: string }).webkitRelativePath;
  return `${path || f.name}:${f.size}:${f.lastModified}`;
}

function addPdfs(fileList: FileList | null) {
  if (!fileList) return;
  const incoming = Array.from(fileList).filter((f) =>
    f.name.toLowerCase().endsWith('.pdf'),
  );
  const existing = new Set(props.pdfFiles.map(fileKey));
  const merged = [...props.pdfFiles];
  for (const f of incoming) {
    if (!existing.has(fileKey(f))) {
      existing.add(fileKey(f));
      merged.push(f);
    }
  }
  emit('update:pdfFiles', merged);
}

function onPdfChange(e: Event) {
  const input = e.target as HTMLInputElement;
  addPdfs(input.files);
  input.value = '';
}
function onFolderChange(e: Event) {
  const input = e.target as HTMLInputElement;
  addPdfs(input.files);
  input.value = '';
}
function removePdf(key: string) {
  emit(
    'update:pdfFiles',
    props.pdfFiles.filter((f) => fileKey(f) !== key),
  );
}
function clearPdfs() {
  emit('update:pdfFiles', []);
}
function onMappingChange(e: Event) {
  const input = e.target as HTMLInputElement;
  emit('update:mappingFile', input.files?.[0] ?? null);
}

const pdfFolders = computed(() => {
  const groups = new Map<string, number>();
  for (const f of props.pdfFiles) {
    const path = (f as File & { webkitRelativePath?: string })
      .webkitRelativePath;
    const folder = path ? path.split('/')[0] : '(individual files)';
    groups.set(folder, (groups.get(folder) ?? 0) + 1);
  }
  return Array.from(groups.entries()).map(([name, count]) => ({ name, count }));
});
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-lg font-semibold">1. Upload files</h2>
      <p class="text-muted-foreground text-sm">
        Add invoice / Gutschrift PDFs and the recipient mapping file, then
        continue to validation.
      </p>
    </div>

    <section class="grid gap-6 sm:grid-cols-2">
      <div class="space-y-2">
        <label class="text-sm font-medium">PDF invoices / Gutschriften</label>
        <p class="text-xs text-muted-foreground">
          Add files or whole folders. Multiple folders / batches are
          aggregated (duplicates ignored).
        </p>
        <div class="flex flex-wrap items-center gap-3">
          <label
            class="cursor-pointer rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90"
          >
            Add files
            <input
              type="file"
              accept="application/pdf"
              multiple
              class="hidden"
              @change="onPdfChange"
            />
          </label>
          <label
            class="cursor-pointer rounded-md border px-3 py-1.5 text-sm hover:bg-accent"
          >
            Add folder
            <input
              type="file"
              webkitdirectory
              directory
              multiple
              class="hidden"
              @change="onFolderChange"
            />
          </label>
          <button
            v-if="pdfFiles.length"
            class="text-xs text-muted-foreground underline"
            @click="clearPdfs"
          >
            Clear all
          </button>
        </div>

        <p class="text-xs text-muted-foreground">
          {{ pdfFiles.length }} PDF(s) selected
        </p>

        <div v-if="pdfFolders.length" class="flex flex-wrap gap-1">
          <Badge
            v-for="g in pdfFolders"
            :key="g.name"
            variant="secondary"
            class="text-xs"
          >
            {{ g.name }}: {{ g.count }}
          </Badge>
        </div>

        <ul
          v-if="pdfFiles.length"
          class="max-h-40 overflow-auto rounded-md border p-2 text-xs space-y-0.5"
        >
          <li
            v-for="f in pdfFiles"
            :key="fileKey(f)"
            class="flex items-center justify-between gap-2"
          >
            <span class="truncate">{{ f.name }}</span>
            <button
              class="shrink-0 text-muted-foreground hover:text-destructive"
              @click="removePdf(fileKey(f))"
            >
              remove
            </button>
          </li>
        </ul>
      </div>

      <div class="space-y-2">
        <label class="text-sm font-medium">Recipient mapping (.xlsx)</label>
        <input
          type="file"
          accept=".xlsx"
          class="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-primary-foreground hover:file:bg-primary/90"
          @change="onMappingChange"
        />
        <p class="text-xs text-muted-foreground">
          {{ mappingFile ? mappingFile.name : 'none selected' }}
        </p>
      </div>
    </section>
  </div>
</template>
