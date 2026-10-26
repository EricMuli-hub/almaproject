const solc=require('solc'),fs=require('fs'),path=require('path');
const src=fs.readFileSync(path.join(__dirname,'../contracts/AlmaRegistry.sol'),'utf8');
const input={language:'Solidity',sources:{'AlmaRegistry.sol':{content:src}},settings:{optimizer:{enabled:process.env.OPT!=='0',runs:200},outputSelection:{'*':{'*':['abi','evm.bytecode.object']}}}};
const out=JSON.parse(solc.compile(JSON.stringify(input)));
const errs=(out.errors||[]).filter(e=>e.severity==='error'); if(errs.length){console.error(errs.map(e=>e.formattedMessage).join('\n'));process.exit(1);}
const c=out.contracts['AlmaRegistry.sol'].AlmaRegistry;
fs.mkdirSync(path.join(__dirname,'../build'),{recursive:true});
fs.writeFileSync(path.join(__dirname,'../build/'+(process.env.OPT==='0'?'AlmaRegistry.noopt.json':'AlmaRegistry.json')),JSON.stringify({abi:c.abi,bytecode:'0x'+c.evm.bytecode.object}));
console.log('compiled, bytecode bytes:',c.evm.bytecode.object.length/2);
