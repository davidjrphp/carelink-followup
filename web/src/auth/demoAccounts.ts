// Demo accounts for the assessment. These tokens match AUTH_TOKENS in .env.example.
// In production this list does not exist: the sign-in page redirects to the OIDC provider.
export interface DemoAccount {
  token: string;
  label: string;
  description: string;
}

export const DEMO_ACCOUNTS: DemoAccount[] = [
  {
    token: 'clin-0101-demo-token',
    label: 'Clinician, Mwansa Urban Clinic',
    description: 'FAC-0101 · reads and records contact attempts · 10,000+ patients on the list',
  },
  {
    token: 'clin-0207-demo-token',
    label: 'Clinician, Kalemba Rural Health Centre',
    description: 'FAC-0207 · reads and records contact attempts',
  },
  {
    token: 'district-demo-token',
    label: 'District officer',
    description: 'All facilities · read-only',
  },
];
