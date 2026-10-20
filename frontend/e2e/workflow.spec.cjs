const {test,expect}=require('@playwright/test');
test('import → queue → evaluate → disposition → replay → frozen suite',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/imports');await page.getByRole('button',{name:'Validate & import evidence'}).click();
 await expect(page.getByRole('heading',{name:'Import report'})).toBeVisible();
 await page.goto('/cases/DEV-VALID-001');await page.getByRole('button',{name:'Evaluate evidence'}).click();
 await expect(page.getByText('Evaluation committed.')).toBeVisible();
 await expect(page.getByText('READY FOR HUMAN REVIEW',{exact:true})).toBeVisible();
 await page.getByLabel('Review note').fill('Reviewed locally in browser test.');
 await page.getByRole('button',{name:'Record disposition'}).click();
 await expect(page.getByText('Disposition recorded.')).toBeVisible();
 await page.getByRole('link',{name:'View trace'}).click();
 await expect(page.getByText('History complete',{exact:false})).toBeVisible();
 await expect(page.getByText('v2: MATCH',{exact:false})).toBeVisible();
 await page.goto('/admin');await page.getByRole('button',{name:'Run 280 policy cases'}).click();
 await expect(page.getByRole('heading',{name:'Evaluation report'})).toBeVisible();
 await expect(page.getByText('"passed": 280',{exact:false})).toBeVisible();
 expect(errors).toEqual([]);
});
test('queue filters persist in URL and case history deep links load',async({page},testInfo)=>{
 await page.goto('/cases');await page.getByLabel('Asset',{exact:true}).fill('AP-100');
 await expect(page).toHaveURL(/asset_id=AP-100/);await expect(page.locator('tbody tr').first()).toContainText('AP-100');
 await page.goto('/cases/DEV-VALID-001/timeline');await expect(page.getByRole('heading',{name:'Version history'})).toBeVisible();
 await page.goto('/cases');await page.screenshot({path:testInfo.outputPath('desktop-queue.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.goto('/cases');
 await expect(page.getByRole('heading',{name:'Fleet review'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
