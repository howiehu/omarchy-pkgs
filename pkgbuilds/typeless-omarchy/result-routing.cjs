// Replay the installed vendor's real completion handler with synthetic fixtures.
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const start = source.indexOf('ra=async(');
const end = source.indexOf(',ur=async', start);
if (start < 0 || end < 0) throw Error('Unsupported vendor result handler');
const handler = source.slice(start + 3, end);
async function run(focused, editable, blocked) {
  const seen = { insert: 0, card: 0 };
  const context = vm.createContext({
    window: { ipcRenderer: { invoke: async () => focused } },
    fr: async () => [{}, {input_capabilities: {is_editable: editable}}],
    _0x1a6f57: () => false,
    _0x3d4afa: async () => { seen.insert++; },
    fe: () => {}, pr: () => {}, _0x17fbcd: {VOICE_COMMAND:'voice_command'},
    hr: async () => !blocked,
    _0x814f0e: async () => { seen.card++; },
  });
  const fn = vm.runInContext('(' + handler + ')', context);
  await fn({refinedText:'Synthetic answer',userPrompt:'Synthetic question',webMetadata:{}}, '');
  return seen;
}
(async () => {
  for (const [name,focused,editable,blocked,expected] of [
    ['No input context, insertion-classified app',false,false,true,{insert:0,card:1}],
    ['No input context, stale editable hint',false,true,false,{insert:0,card:1}],
    ['Focused editable input preserves vendor routing',true,true,false,{insert:1,card:0}],
  ]) {
    const actual = await run(focused,editable,blocked);
    if (JSON.stringify(actual)!==JSON.stringify(expected)) throw Error(name+': '+JSON.stringify(actual)+' expected '+JSON.stringify(expected));
    console.log('PASS: '+name);
  }
})().catch(error=>{console.error(error.message);process.exit(1)});
