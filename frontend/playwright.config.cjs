const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({testDir:'e2e',workers:1,use:{baseURL:'http://127.0.0.1:8000',headless:true},reporter:[['list'],['json',{outputFile:'../reports/playwright.json'}]]});
