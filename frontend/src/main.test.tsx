import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,cleanup} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {MemoryRouter} from 'react-router-dom';
import {Badge,LoadState,App} from './main';
import {api} from './api';
afterEach(()=>{cleanup();vi.restoreAllMocks()});
describe('decision display and API boundary',()=>{
 it('shows the exact backend review state as text',()=>{render(<Badge state="READY_FOR_HUMAN_REVIEW"/>);expect(screen.getByText('READY FOR HUMAN REVIEW')).toBeInTheDocument()});
 it('shows an error instead of an empty result',()=>{render(<LoadState loading={false} error="Database unavailable"/>);expect(screen.getByRole('alert')).toHaveTextContent('Database unavailable')});
 it('shows loading explicitly',()=>{render(<LoadState loading error=""/>);expect(screen.getByRole('status')).toHaveTextContent('Loading records')});
 it('sends idempotency and expected version headers',async()=>{const mock=vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response(JSON.stringify({ok:true})));await api('/cases/x/evaluations',{},3,'fixed-key');const options=mock.mock.calls[0][1]!;expect(options.headers).toMatchObject({'If-Match':'3','Idempotency-Key':'fixed-key'});expect(options.body).toBe('{}')});
 it('rejects server errors with a visible safe message',async()=>{vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response(JSON.stringify({error:{code:'STALE_VERSION',message:'Refresh case'}}),{status:409}));await expect(api('/cases/x/evaluations',{},1)).rejects.toThrow('STALE_VERSION: Refresh case')});
 it('renders a failed case GET as an alert without an empty queue',async()=>{vi.spyOn(globalThis,'fetch').mockImplementation(async(url)=>String(url).endsWith('/session')?new Response(JSON.stringify({principal:'tester',role:'planner',capabilities:['read']})):new Response(JSON.stringify({error:{code:'OPERATION_FAILED',message:'Database unavailable'}}),{status:500}));render(<MemoryRouter initialEntries={['/cases']}><App/></MemoryRouter>);expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable');expect(screen.queryByText('No cases match this view')).not.toBeInTheDocument()});
});
