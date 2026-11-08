import { Award, FilePen, FileStack, IdCard, Landmark, MapPinHouse, ScrollText } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '../../../lib/cn'
import { DocumentUploadField } from './DocumentUploadField'
import { DOCUMENT_CATALOGUE, documentsFor } from './types'
import type { DocumentErrors, DocumentFiles, DocumentId, OrganizationCategory } from './types'

/** An icon per document, so each tile is recognisable without reading its description. */
const DOCUMENT_ICONS: Record<DocumentId, LucideIcon> = {
  adminId: IdCard,
  officeOrder: FilePen,
  registration: ScrollText,
  lguEndorsement: Landmark,
  accreditation: Award,
  proofOfAddress: MapPinHouse,
  otherSupporting: FileStack,
}

interface DocumentsStepProps {
  category: OrganizationCategory
  files: DocumentFiles
  errors: DocumentErrors
  onDocumentChange: (id: DocumentId, file: File | null, error: string | null) => void
  agreedToTerms: boolean
  onTermsChange: (checked: boolean) => void
}

export function DocumentsStep({
  category,
  files,
  errors,
  onDocumentChange,
  agreedToTerms,
  onTermsChange,
}: DocumentsStepProps) {
  const docs = documentsFor(category)
  const required = docs.filter((doc) => doc.requirement === 'required')
  const oneOf = docs.filter((doc) => doc.requirement === 'oneOf')
  const optional = docs.filter((doc) => doc.requirement === 'optional')

  return (
    <div className="flex flex-col gap-3">
      <p className="text-right text-xs text-foreground-muted">PDF, PNG, or JPG · max 10 MB per file</p>

      {required.length > 0 ? (
        <section className="flex flex-col gap-2" aria-labelledby="required-documents-heading">
          <div>
            <h3 id="required-documents-heading" className="text-sm font-semibold text-foreground">
              Required documents <span className="text-danger" aria-hidden="true">*</span>
            </h3>
            <p className="text-xs text-danger-fg">Every document marked in red must be uploaded before you can submit.</p>
          </div>
          <div className="grid grid-cols-2 gap-2.5 @md:grid-cols-4">
            {required.map(({ id }) => {
              const doc = DOCUMENT_CATALOGUE[id]
              return (
                <DocumentUploadField
                  key={id}
                  id={`doc-${id}`}
                  icon={DOCUMENT_ICONS[id]}
                  label={doc.shortLabel}
                  tooltip={`${doc.label} — ${doc.hint}`}
                  required
                  file={files[id]}
                  error={errors[id]}
                  onChange={(file, error) => onDocumentChange(id, file, error)}
                />
              )
            })}
          </div>
        </section>
      ) : null}

      {oneOf.length > 0 ? (
        <section
          className="flex flex-col gap-2 border-t border-border/70 pt-3"
          aria-labelledby="one-of-documents-heading"
        >
          <div>
            <h3 id="one-of-documents-heading" className="text-sm font-semibold text-foreground">
              Supporting documents
            </h3>
            <p className="text-xs text-foreground-secondary">Upload at least one of these.</p>
          </div>
          <div className="grid grid-cols-2 gap-2.5 @md:grid-cols-4">
            {oneOf.map(({ id }) => {
              const doc = DOCUMENT_CATALOGUE[id]
              return (
                <DocumentUploadField
                  key={id}
                  id={`doc-${id}`}
                  icon={DOCUMENT_ICONS[id]}
                  label={doc.shortLabel}
                  tooltip={`${doc.label} — ${doc.hint}`}
                  file={files[id]}
                  error={errors[id]}
                  onChange={(file, error) => onDocumentChange(id, file, error)}
                />
              )
            })}
          </div>
        </section>
      ) : null}

      {optional.length > 0 ? (
        <section
          className={cn(
            'flex flex-col gap-2',
            (required.length > 0 || oneOf.length > 0) && 'border-t border-border/70 pt-3',
          )}
          aria-labelledby="optional-documents-heading"
        >
          <h3 id="optional-documents-heading" className="text-sm font-semibold text-foreground">
            Optional documents
          </h3>
          <div className="grid grid-cols-2 gap-2.5 @md:grid-cols-4">
            {optional.map(({ id }) => {
              const doc = DOCUMENT_CATALOGUE[id]
              return (
                <DocumentUploadField
                  key={id}
                  id={`doc-${id}`}
                  icon={DOCUMENT_ICONS[id]}
                  label={doc.shortLabel}
                  tooltip={`${doc.label} — ${doc.hint}`}
                  file={files[id]}
                  error={errors[id]}
                  onChange={(file, error) => onDocumentChange(id, file, error)}
                />
              )
            })}
          </div>
        </section>
      ) : null}

      <label htmlFor="terms" className="flex items-start gap-2 text-sm leading-relaxed text-foreground-secondary">
        <input
          id="terms"
          type="checkbox"
          checked={agreedToTerms}
          onChange={(event) => onTermsChange(event.target.checked)}
          className="mt-0.5 size-4 shrink-0 rounded border-border-strong [accent-color:var(--color-accent)]"
        />
        <span>
          I certify that the information and documents provided are accurate, and I agree to the{' '}
          <a href="#" className="font-medium text-accent hover:underline">
            Terms of Service
          </a>{' '}
          and{' '}
          <a href="#" className="font-medium text-accent hover:underline">
            Privacy Policy
          </a>
          .
        </span>
      </label>
    </div>
  )
}
